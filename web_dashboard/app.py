#!/usr/bin/env python3
"""
Dashboard + REST API - Red Mesh Descentralizada ProyectoSC
"""

import sys, os, time, threading, uuid, queue
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, request, abort, Response, stream_with_context
import db
import node_config as _cfg
import urllib.request
import json as _json

# ─── SSE: cola de eventos del juego ──────────────────────────────────────────
# Cada cliente SSE conectado recibe su propia Queue.
# Cuando el estado del juego cambia, _push_game_event() pone el nuevo estado
# en todas las colas activas y los clientes lo reciben al instante.
_sse_clients: list[queue.Queue] = []
_sse_lock = threading.Lock()

def _push_game_event(state: dict):
    """Empuja estado del juego a todos los clientes SSE conectados."""
    data = 'data: ' + _json.dumps(state) + '\n\n'
    with _sse_lock:
        dead = []
        for q in _sse_clients:
            try:
                q.put_nowait(data)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)

# ─── PEERS ───────────────────────────────────────────────────────────────────
# Solo nodos vistos en los últimos NODE_TIMEOUT segundos se consideran activos
NODE_TIMEOUT = 30  # segundos sin anuncio → nodo se considera offline

def _get_peers() -> dict[str, str]:
    """Retorna {node_name: ip} de nodos activos (vistos hace menos de NODE_TIMEOUT s)."""
    nodes = db.get_known_nodes()
    now = time.time()
    peers = {
        n['name']: n['bat0_ip']
        for n in nodes
        if n.get('bat0_ip') and (now - n.get('last_seen', 0)) < NODE_TIMEOUT
    }
    if not peers:
        c = _cfg.load()
        peers[c['node_name']] = c.get('bat0_ip', '')
    return peers


# ─── Heartbeat propio: actualizar last_seen en DB cada 10s ──────────────────
def _heartbeat_loop():
    def loop():
        while True:
            time.sleep(10)
            c = _cfg.load()
            try:
                db.upsert_node_ip(c['node_name'], c.get('bat0_ip', ''), c.get('role', 'cliente'))
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True).start()


# ─── Limpieza de jugadores desconectados ─────────────────────────────────────
def _game_watchdog_loop():
    """Cada 15s revisa si hay jugadores offline en la partida activa y los saca."""
    def loop():
        while True:
            time.sleep(15)
            try:
                state = db.get_active_game()
                if not state or state.get('phase') == 'finished':
                    continue
                # Nodos online según last_seen
                online = {n['name'] for n in db.get_known_nodes()
                          if time.time() - n.get('last_seen', 0) < NODE_TIMEOUT}
                c = _cfg.load()
                my_name = c['node_name']
                my_ip   = c.get('bat0_ip', '')
                # Solo actuar si este nodo es el dealer (evitar que todos hagan lo mismo)
                if state.get('dealer') != my_name:
                    continue
                removed = [name for name in list(state['players'])
                           if name not in online and name != my_name]
                if not removed:
                    continue
                for name in removed:
                    state['players'].pop(name)
                state['version'] = state.get('version', 1) + 1
                if not state['players']:
                    db.clear_old_games()
                    _push_game_event({})
                    threading.Thread(target=_broadcast_game, args=({}, my_ip), daemon=True).start()
                else:
                    all_done = all(p['status'] != 'playing' for p in state['players'].values())
                    if all_done:
                        state = _resolve_dealer(state)
                    db.upsert_game(state['game_id'], state)
                    _push_game_event(state)
                    threading.Thread(target=_broadcast_game, args=(state, my_ip), daemon=True).start()
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True).start()

app = Flask(__name__)
app.config['LOG_FILE'] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "sensor.log"
)

db.init_db()
_heartbeat_loop()
_game_watchdog_loop()

# ─── PÁGINAS ─────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    c = _cfg.load()
    return render_template('dashboard.html', node_name=c['node_name'], role=c['role'])

# ─── API ROL ──────────────────────────────────────────────────────────────────

@app.route('/api/role', methods=['GET'])
def api_get_role():
    c = _cfg.load()
    return jsonify({
        "role":      c['role'],
        "node_name": c['node_name'],
        "bat0_ip":   c.get('bat0_ip', ''),
    })

# ─── API NODOS ────────────────────────────────────────────────────────────────

@app.route('/api/node-announce', methods=['POST'])
def api_node_announce():
    """Recibe heartbeat/anuncio de un nodo remoto y actualiza su last_seen."""
    data = request.get_json(force=True)
    name    = data.get('node_name', '').strip()
    role    = data.get('role', 'peer').lower()
    bat0_ip = data.get('bat0_ip', '').strip()
    if not name:
        abort(400, description="node_name requerido")
    db.upsert_node_ip(name, bat0_ip, role)
    return jsonify({"ok": True, "node_name": name, "role": role, "bat0_ip": bat0_ip})

# ─── API TRANSACCIONES ────────────────────────────────────────────────────────

@app.route('/api/transactions', methods=['GET'])
def api_transactions():
    limit = int(request.args.get('limit', 100))
    node  = request.args.get('node')
    return jsonify(db.get_transactions(limit, node=node))

@app.route('/api/transactions', methods=['POST'])
def api_create_transaction():
    data = request.get_json(force=True)
    for f in ('message_id', 'origin_node', 'action', 'sku'):
        if not data.get(f):
            abort(400, description=f"Campo requerido: {f}")
    now = time.time()
    tx = {
        'message_id':         data['message_id'],
        'origin_node':        data['origin_node'],
        'action':             data['action'],
        'sku':                data['sku'],
        'quantity_delta':     data.get('quantity_delta', 1),
        'timestamp_created':  data.get('timestamp_created', now),
        'timestamp_received': now,
        'latency_ms':         max(0, (now - data.get('timestamp_created', now)) * 1000),
        'payload':            str(data.get('payload', '')),
        'node_role':          data.get('node_role', 'cliente'),
    }
    inserted = db.insert_transaction(tx)
    return jsonify({'inserted': inserted, 'message_id': tx['message_id']}), (201 if inserted else 200)

# ─── API MÉTRICAS / ESTADO ───────────────────────────────────────────────────

@app.route('/api/metrics')
def api_metrics():
    metrics = db.get_metrics()
    c = _cfg.load()
    metrics['node_name'] = c['node_name']
    metrics['role']      = c['role']
    metrics['timestamp'] = time.time()
    metrics['status']    = 'online'
    resp = jsonify(metrics)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

@app.route('/api/network-topology')
def api_topology():
    metrics = db.get_metrics()
    return jsonify({
        'nodes': metrics['nodes'],
        'by_node': metrics['by_node'],
        'total_packets': metrics['total_transactions'],
    })

@app.route('/api/peers-metrics')
def api_peers_metrics():
    """Métricas de todos los nodos activos vía HTTP."""
    peers = _get_peers()
    c = _cfg.load()
    my_ip = c.get('bat0_ip', '')
    results = []
    for name, ip in peers.items():
        fetch_url = 'http://127.0.0.1:5080/api/metrics' if ip == my_ip else f'http://{ip}:5080/api/metrics'
        try:
            req = urllib.request.Request(fetch_url)
            with urllib.request.urlopen(req, timeout=2) as r:
                data = _json.loads(r.read())
                data['peer_ip'] = ip
                data['status']  = 'online'
                data['node_name'] = name
                results.append(data)
        except Exception:
            results.append({'node_name': name, 'peer_ip': ip, 'status': 'offline',
                            'total_transactions': 0, 'avg_latency_ms': 0, 'rho': 0})
    return jsonify(results)

@app.route('/api/shutdown-node', methods=['POST'])
def api_shutdown_node():
    import subprocess
    def do_shutdown():
        time.sleep(1)
        try:
            subprocess.run(['sudo', 'systemctl', 'start', 'NetworkManager'], check=False)
            subprocess.run(['sudo', 'ip', 'link', 'set', 'bat0', 'down'], check=False)
            subprocess.run(['sudo', 'modprobe', '-r', 'batman-adv'], check=False)
        except Exception:
            pass
        os.kill(os.getpid(), 9)
    threading.Thread(target=do_shutdown, daemon=True).start()
    return jsonify({'ok': True, 'message': 'Nodo apagándose…'})

@app.route('/api/traceroute-all')
def api_traceroute_all():
    peers = _get_peers()
    c = _cfg.load()
    my_ip = c.get('bat0_ip', '')
    all_routes = []
    for name, ip in peers.items():
        fetch_ip = my_ip if ip == my_ip else ip
        try:
            req = urllib.request.Request(f'http://{fetch_ip}:5080/api/traceroute')
            with urllib.request.urlopen(req, timeout=3) as r:
                all_routes.extend(_json.loads(r.read()))
        except Exception:
            pass
    seen = {}
    for r in all_routes:
        key = tuple(sorted([r['src'], r['dst']]))
        if key not in seen:
            seen[key] = r
    return jsonify(list(seen.values()))

@app.route('/api/ping-all')
def api_ping_all():
    peers = _get_peers()
    c = _cfg.load()
    my_ip = c.get('bat0_ip', '')
    online_nodes, all_pings, seen_pairs = set(), [], set()
    for name, ip in peers.items():
        fetch_url = 'http://127.0.0.1:5080/api/ping-stats' if ip == my_ip else f'http://{ip}:5080/api/ping-stats'
        try:
            req = urllib.request.Request(fetch_url)
            with urllib.request.urlopen(req, timeout=2) as r:
                pings = _json.loads(r.read())
                online_nodes.add(name)
                for p in pings:
                    key = tuple(sorted([p['src'], p['dst']]))
                    if key not in seen_pairs:
                        seen_pairs.add(key)
                        all_pings.append(p)
        except Exception:
            pass
    return jsonify([p for p in all_pings if p.get('src') in online_nodes and p.get('dst') in online_nodes])

@app.route('/api/ping-stats')
def api_ping_stats():
    import subprocess, re
    peers = _get_peers()
    c = _cfg.load()
    my_ip   = c.get('bat0_ip', '')
    my_name = c.get('node_name', 'Nodo')
    results = []
    for name, ip in peers.items():
        if ip == my_ip:
            continue
        try:
            out = subprocess.check_output(
                ['ping', '-c', '4', '-W', '1', '-i', '0.2', ip],
                timeout=5, stderr=subprocess.DEVNULL
            ).decode()
            m      = re.search(r'(\d+\.?\d*)/(\d+\.?\d*)/(\d+\.?\d*)/(\d+\.?\d*)', out)
            lost_m = re.search(r'(\d+)%\s+packet loss', out)
            rtt_min = rtt_avg = rtt_max = rtt_mdev = None
            if m:
                rtt_min, rtt_avg, rtt_max, rtt_mdev = (float(m.group(i)) for i in range(1,5))
            loss_pct = int(lost_m.group(1)) if lost_m else 100
            dist_label, dist_m = '—', None
            if rtt_avg is not None and loss_pct < 100:
                prop = max(0, rtt_avg - 1.0)
                if prop < 1:   dist_label, dist_m = 'Muy cerca (<10m)',           '<10'
                elif prop < 3: dist_label, dist_m = 'Cerca (~10-30m)',             '10-30'
                elif prop < 8: dist_label, dist_m = 'Medio (~30-80m)',             '30-80'
                elif prop < 20:dist_label, dist_m = 'Lejos (~80-150m)',            '80-150'
                else:          dist_label, dist_m = 'Muy lejos / multisalto (>150m)', '>150'
            results.append({
                'src': my_name, 'dst': name, 'dst_ip': ip,
                'rtt_min': rtt_min, 'rtt_avg': rtt_avg,
                'rtt_max': rtt_max, 'rtt_mdev': rtt_mdev,
                'loss_pct': loss_pct, 'reachable': loss_pct < 100,
                'dist_label': dist_label, 'dist_m': dist_m,
            })
        except Exception:
            results.append({
                'src': my_name, 'dst': name, 'dst_ip': ip,
                'rtt_avg': None, 'loss_pct': 100,
                'reachable': False, 'dist_label': 'Sin respuesta', 'dist_m': None,
            })
    return jsonify(results)

@app.route('/api/traceroute')
def api_traceroute():
    import subprocess
    c = _cfg.load()
    targets = _get_peers()
    my_ip   = c.get('bat0_ip', '')
    my_name = c.get('node_name', 'Nodo')
    results = []
    for name, ip in targets.items():
        if ip == my_ip:
            continue
        try:
            out = subprocess.check_output(
                ['traceroute', '-n', '-m', '5', '-w', '1', '-q', '1', ip],
                timeout=8, stderr=subprocess.DEVNULL
            ).decode()
            hops = []
            for line in out.strip().split('\n')[1:]:
                parts = line.split()
                hop_ip = next((p for p in parts if p.count('.') == 3), None)
                lat    = next((p for p in parts if p.replace('.','').isdigit()), None)
                if hop_ip:
                    hops.append({'ip': hop_ip, 'ms': lat or '?'})
            reachable = bool(hops) and hops[-1]['ip'] == ip
            results.append({
                'src': my_name, 'dst': name, 'dst_ip': ip,
                'hops': hops, 'hop_count': len(hops),
                'reachable': reachable,
                'latency_ms': hops[-1]['ms'] if hops else None,
            })
        except Exception:
            results.append({
                'src': my_name, 'dst': name, 'dst_ip': ip,
                'hops': [], 'hop_count': 0, 'reachable': False, 'latency_ms': None,
            })
    return jsonify(results)

@app.route('/api/logs')
def api_logs():
    try:
        with open(app.config['LOG_FILE'], 'r') as f:
            lines = f.readlines()[-100:]
    except Exception:
        lines = []
    return jsonify({'logs': lines})

# ─── CHAT ────────────────────────────────────────────────────────────────────

@app.route('/api/chat/messages', methods=['GET'])
def api_chat_get():
    since = float(request.args.get('since', 0))
    return jsonify(db.get_chat(since=since, limit=200))

@app.route('/api/chat/sync', methods=['POST'])
def api_chat_sync():
    """Recibe un lote de mensajes de chat de un peer y los inserta si no existen."""
    msgs = request.get_json(force=True)
    if not isinstance(msgs, list):
        abort(400, description="Se esperaba lista de mensajes")
    inserted = 0
    for m in msgs:
        msg_id    = m.get('msg_id', '').strip()
        from_node = m.get('from_node', '').strip()
        to_node   = m.get('to_node', 'all').strip()
        body      = m.get('body', '').strip()
        ts_val    = m.get('ts', time.time())
        if not msg_id or not from_node or not body:
            continue
        try:
            with db._db_lock:
                conn = db.get_conn()
                conn.execute(
                    "INSERT OR IGNORE INTO chat_messages(msg_id,from_node,to_node,body,ts) VALUES(?,?,?,?,?)",
                    (msg_id, from_node, to_node, body, ts_val)
                )
                conn.commit()
            inserted += 1
        except Exception:
            pass
    return jsonify({'ok': True, 'inserted': inserted})

def _relay_chat(payload_bytes: bytes, peers: dict, my_ip: str):
    """Envía el mensaje a cada peer en un hilo separado, fire-and-forget."""
    def send_to(ip):
        try:
            req = urllib.request.Request(
                f'http://{ip}:5080/api/chat/send', data=payload_bytes,
                method='POST', headers={'Content-Type': 'application/json'}
            )
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass  # peer inalcanzable — el poll del destinatario lo ignorará

    for name, ip in peers.items():
        if ip == my_ip:
            continue
        threading.Thread(target=send_to, args=(ip,), daemon=True).start()


@app.route('/api/chat/send', methods=['POST'])
def api_chat_send():
    """Persiste un mensaje de chat y lo reenvía a todos los peers (no bloquea)."""
    data      = request.get_json(force=True)
    msg_id    = data.get('msg_id') or str(uuid.uuid4())
    from_node = data.get('from_node', '').strip()
    to_node   = data.get('to_node', 'all').strip()
    body      = data.get('body', '').strip()
    if not from_node or not body:
        abort(400, description="from_node y body requeridos")

    inserted = db.insert_chat(msg_id, from_node, to_node, body)

    # Relay a peers solo si es mensaje propio y no es ya un relay
    c = _cfg.load()
    my_name = c.get('node_name', '')
    if inserted and from_node == my_name and not data.get('_relay'):
        payload = _json.dumps({
            'msg_id': msg_id, 'from_node': from_node,
            'to_node': to_node, 'body': body, '_relay': True
        }).encode()
        threading.Thread(
            target=_relay_chat,
            args=(payload, _get_peers(), c.get('bat0_ip', '')),
            daemon=True
        ).start()

    return jsonify({'ok': True, 'inserted': inserted, 'msg_id': msg_id})

# ─── GAME ────────────────────────────────────────────────────────────────────
import random as _random

SUITS  = ['♠','♥','♦','♣']
VALUES = ['A','2','3','4','5','6','7','8','9','10','J','Q','K']

def _new_deck():
    deck = [{'suit': s, 'val': v} for s in SUITS for v in VALUES]
    _random.shuffle(deck)
    return deck

def _card_points(val):
    if val in ('J','Q','K'): return 10
    if val == 'A': return 11
    return int(val)

def _hand_total(hand):
    total = sum(_card_points(c['val']) for c in hand)
    aces  = sum(1 for c in hand if c['val'] == 'A')
    while total > 21 and aces:
        total -= 10
        aces  -= 1
    return total

def _broadcast_game(state: dict, my_ip: str):
    """Propaga el estado de la partida a todos los peers en hilos independientes."""
    peers = _get_peers()
    payload = _json.dumps(state).encode()
    def send(ip):
        try:
            req = urllib.request.Request(
                f'http://{ip}:5080/api/game/sync',
                data=payload, method='POST',
                headers={'Content-Type': 'application/json'}
            )
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass  # peer inalcanzable — el poll del cliente lo recogerá igual
    for name, ip in peers.items():
        if ip == my_ip:
            continue
        threading.Thread(target=send, args=(ip,), daemon=True).start()


@app.route('/game')
def game_page():
    c = _cfg.load()
    return render_template('game.html', node_name=c['node_name'], role=c['role'])


@app.route('/api/game/state', methods=['GET'])
def api_game_state():
    state = db.get_active_game()
    return jsonify(state or {})


@app.route('/api/game/leave', methods=['POST'])
def api_game_leave():
    """Saca al jugador de la partida activa. Si no quedan jugadores, borra la partida."""
    c = _cfg.load()
    my_name = c['node_name']
    my_ip   = c.get('bat0_ip', '')

    state = db.get_active_game()
    if not state or my_name not in state.get('players', {}):
        return jsonify({'ok': True, 'msg': 'no estaba en partida'})

    # Devolver apuesta si aún estaba jugando
    p = state['players'].pop(my_name)
    if p.get('status') == 'playing':
        pass  # créditos ya descontados, se pierden al salir a mitad

    state['version'] = state.get('version', 1) + 1

    if not state['players']:
        def _bg_leave():
            db.clear_old_games()
            _push_game_event({})
            _broadcast_game({}, my_ip)
    else:
        if state['dealer'] == my_name:
            state['dealer'] = next(iter(state['players']))
        all_done = all(p2['status'] != 'playing' for p2 in state['players'].values())
        if all_done and state['phase'] == 'playing':
            state = _resolve_dealer(state)
        _s = state
        def _bg_leave():
            db.upsert_game(_s['game_id'], _s)
            _push_game_event(_s)
            _broadcast_game(_s, my_ip)

    threading.Thread(target=_bg_leave, daemon=True).start()
    return jsonify({'ok': True})


@app.route('/api/game/reset', methods=['POST'])
def api_game_reset():
    """Borra la partida activa — cualquier jugador puede llamarlo."""
    c = _cfg.load()
    my_ip = c.get('bat0_ip', '')
    def _bg_reset():
        db.clear_old_games()
        _push_game_event({})
        _broadcast_game({}, my_ip)
    threading.Thread(target=_bg_reset, daemon=True).start()
    return jsonify({'ok': True})


@app.route('/api/game/events')
def api_game_events():
    """SSE stream — emite estado del juego en tiempo real."""
    q = queue.Queue(maxsize=20)
    with _sse_lock:
        _sse_clients.append(q)

    # Enviar estado actual inmediatamente al conectar
    current = db.get_active_game()
    initial = 'data: ' + _json.dumps(current or {}) + '\n\n'

    @stream_with_context
    def generate():
        try:
            yield initial
            while True:
                try:
                    data = q.get(timeout=25)  # heartbeat cada 25s si no hay eventos
                    yield data
                except queue.Empty:
                    yield ': heartbeat\n\n'  # keep-alive para que el proxy no cierre
        finally:
            with _sse_lock:
                try:
                    _sse_clients.remove(q)
                except ValueError:
                    pass

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/game/sync', methods=['POST'])
def api_game_sync():
    """Recibe estado de partida propagado por otro nodo."""
    state = request.get_json(force=True)
    game_id = state.get('game_id')
    if not game_id:
        # Estado vacío = reset propagado por otro nodo
        db.clear_old_games()
        _push_game_event({})
        return jsonify({'ok': True})
    existing = db.get_game(game_id)
    if not existing or state.get('version', 0) >= existing.get('version', 0):
        db.upsert_game(game_id, state)
        _push_game_event(state)
    return jsonify({'ok': True})


@app.route('/api/game/create', methods=['POST'])
def api_game_create():
    """Crea una nueva partida. El nodo que llama es el dealer."""
    c = _cfg.load()
    my_name = c['node_name']
    my_ip   = c.get('bat0_ip', '')
    data    = request.get_json(force=True) or {}
    bet     = max(10, int(data.get('bet', 100)))

    deck    = _new_deck()
    game_id = str(uuid.uuid4())[:8]
    dealer_hand = [deck.pop(), deck.pop()]

    state = {
        'game_id':     game_id,
        'version':     1,
        'phase':       'waiting',
        'dealer':      my_name,
        'dealer_hand': dealer_hand,
        'dealer_hidden': True,
        'deck':        deck,
        'players': {
            my_name: {
                'hand':    [deck.pop(), deck.pop()],
                'bet':     bet,
                'credits': data.get('credits', 1000) - bet,
                'status':  'playing',
                'result':  None,
            }
        },
        'created_at':  time.time(),
        'finished_at': None,
    }

    # Persistir y notificar en background — respondemos al cliente YA
    def _persist_and_broadcast():
        db.clear_old_games()
        db.upsert_game(game_id, state)
        _push_game_event(state)
        _broadcast_game(state, my_ip)

    threading.Thread(target=_persist_and_broadcast, daemon=True).start()
    return jsonify(state)  # el cliente ve el estado al instante


@app.route('/api/game/join', methods=['POST'])
def api_game_join():
    """Un nodo se une a la partida activa."""
    c = _cfg.load()
    my_name = c['node_name']
    my_ip   = c.get('bat0_ip', '')
    data    = request.get_json(force=True) or {}
    bet     = max(10, int(data.get('bet', 100)))

    state = db.get_active_game()
    if not state:
        abort(404, description="No hay partida activa")
    if state['phase'] not in ('waiting', 'playing'):
        abort(409, description="La partida ya no acepta jugadores")
    if my_name in state['players']:
        return jsonify(state)  # ya está en la partida

    deck = state['deck']
    state['players'][my_name] = {
        'hand':    [deck.pop(), deck.pop()],
        'bet':     bet,
        'credits': data.get('credits', 1000) - bet,
        'status':  'playing',
        'result':  None,
    }
    state['deck']    = deck
    state['phase']   = 'playing'
    state['version'] = state.get('version', 1) + 1

    def _persist_join():
        db.upsert_game(state['game_id'], state)
        _push_game_event(state)
        _broadcast_game(state, my_ip)

    threading.Thread(target=_persist_join, daemon=True).start()
    return jsonify(state)


@app.route('/api/game/action', methods=['POST'])
def api_game_action():
    """hit | stand | double del jugador."""
    c = _cfg.load()
    my_name = c['node_name']
    my_ip   = c.get('bat0_ip', '')
    data    = request.get_json(force=True) or {}
    action  = data.get('action', '').lower()

    state = db.get_active_game()
    if not state:
        abort(404, description="No hay partida activa")
    if state['phase'] not in ('playing',):
        abort(409, description=f"Acción no permitida en fase: {state['phase']}")
    if my_name not in state['players']:
        abort(403, description="No estás en esta partida")

    player = state['players'][my_name]
    if player['status'] != 'playing':
        abort(409, description="Ya tomaste tu decisión")

    deck = state['deck']

    if action == 'hit':
        player['hand'].append(deck.pop())
        state['deck'] = deck
        total = _hand_total(player['hand'])
        if total > 21:
            player['status'] = 'bust'
        elif total == 21:
            player['status'] = 'stand'

    elif action == 'stand':
        player['status'] = 'stand'

    elif action == 'double':
        if len(player['hand']) != 2:
            abort(409, description="Double solo en primera jugada")
        player['credits'] -= player['bet']
        player['bet']     *= 2
        player['hand'].append(deck.pop())
        state['deck'] = deck
        total = _hand_total(player['hand'])
        player['status'] = 'bust' if total > 21 else 'stand'

    state['players'][my_name] = player
    state['version'] = state.get('version', 1) + 1

    # Verificar si todos terminaron → resolver inmediatamente (sin esperar click del dealer)
    all_done = all(p['status'] != 'playing' for p in state['players'].values())
    if all_done:
        state = _resolve_dealer(state)

    _state_snap = state  # capturar referencia antes del thread
    def _persist_action():
        db.upsert_game(_state_snap['game_id'], _state_snap)
        _push_game_event(_state_snap)
        _broadcast_game(_state_snap, my_ip)

    threading.Thread(target=_persist_action, daemon=True).start()
    return jsonify(state)


@app.route('/api/game/dealer-resolve', methods=['POST'])
def api_game_dealer_resolve():
    """El dealer ejecuta su turno y cierra la partida (solo lo llama el dealer)."""
    c = _cfg.load()
    my_name = c['node_name']
    my_ip   = c.get('bat0_ip', '')

    state = db.get_active_game()
    if not state:
        abort(404, description="No hay partida activa")
    if state['dealer'] != my_name:
        abort(403, description="Solo el dealer puede resolver")

    state = _resolve_dealer(state)
    db.upsert_game(state['game_id'], state)
    _push_game_event(state)
    threading.Thread(target=_broadcast_game, args=(state, my_ip), daemon=True).start()
    return jsonify(state)


def _resolve_dealer(state: dict) -> dict:
    """Dealer juega según reglas (hit ≤16, stand ≥17) y calcula resultados."""
    deck = state['deck']
    hand = state['dealer_hand']
    state['dealer_hidden'] = False

    while _hand_total(hand) < 17:
        hand.append(deck.pop())

    state['dealer_hand'] = hand
    state['deck']        = deck
    dealer_total         = _hand_total(hand)
    dealer_bust          = dealer_total > 21

    for name, player in state['players'].items():
        p_total = _hand_total(player['hand'])
        p_bj    = p_total == 21 and len(player['hand']) == 2

        if player['status'] == 'bust':
            player['result'] = 'bust'
        elif p_bj and not (dealer_total == 21 and len(state['dealer_hand']) == 2):
            player['result']   = 'blackjack'
            player['credits'] += int(player['bet'] * 2.5)
        elif dealer_bust or p_total > dealer_total:
            player['result']   = 'win'
            player['credits'] += player['bet'] * 2
        elif p_total == dealer_total:
            player['result']   = 'push'
            player['credits'] += player['bet']
        else:
            player['result'] = 'lose'

        state['players'][name] = player

    state['phase']       = 'finished'
    state['finished_at'] = time.time()
    state['version']     = state.get('version', 1) + 1
    return state


# ─── ERROR HANDLERS ──────────────────────────────────────────────────────────

@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(409)
@app.errorhandler(503)
def handle_error(e):
    return jsonify({'error': str(e.description)}), e.code


if __name__ == '__main__':
    c = _cfg.load()
    print(f"Dashboard iniciado — {c['node_name']} rol={c['role']}")
    print("Acceso: http://localhost:5080")
    app.run(host='0.0.0.0', port=int(os.getenv('DASHBOARD_PORT', 5080)),
            debug=False, threaded=True)
