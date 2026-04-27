#!/usr/bin/env python3
"""
Dashboard + REST API - Sistema de Gestión de Inventario Descentralizado
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, request, abort
import db
import node_config as _cfg
import time
import uuid
import urllib.request
import json as _json

# ─── ROLES ───────────────────────────────────────────────────────────────────
# admin   → todo: leer, escribir, cambiar roles, sync
# servidor → replica BD del master, sirve lecturas, redirige escrituras al master
# cliente  → solo lectura, redirige todo lo demás al master

ROLES = {
    "admin":    {"can_write": True,  "can_read": True,  "is_authority": True},
    "servidor": {"can_write": False, "can_read": True,  "is_authority": False},
    "cliente":  {"can_write": False, "can_read": True,  "is_authority": False},
    # roles legacy del sensor
    "master":   {"can_write": True,  "can_read": True,  "is_authority": True},
    "replica":  {"can_write": False, "can_read": True,  "is_authority": False},
}

def _role():
    return _cfg.get("role", "cliente")

def _can_write():
    return ROLES.get(_role(), {}).get("can_write", False)

def _is_authority():
    return ROLES.get(_role(), {}).get("is_authority", False)

def _master_url():
    master_ip = _cfg.get("master_ip") or ""
    if not master_ip:
        return None
    return f"http://{master_ip}:5080"

def _proxy_to_master(path, method="GET", body=None):
    url = _master_url()
    if not url:
        return None
    full = url + path
    data = _json.dumps(body).encode() if body else None
    req = urllib.request.Request(full, data=data, method=method,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return _json.loads(r.read())

def _sync_from_master():
    """Pull items del master y actualiza BD local."""
    try:
        items = _proxy_to_master('/api/items')
        if not items:
            return 0
        synced = 0
        for item in items:
            existing = db.get_item(item['sku'])
            if not existing:
                db.create_item(item)
                synced += 1
            elif existing['quantity'] != item['quantity']:
                db.update_item(item['sku'], {'quantity': item['quantity']})
                synced += 1
        return synced
    except Exception:
        return 0


app = Flask(__name__)
app.config['NODE_NAME'] = os.getenv('NODE_NAME', 'Node-1')
app.config['LOG_FILE']  = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "sensor.log")

db.init_db()

# ─── PÁGINAS ────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    c = _cfg.load()
    return render_template('dashboard.html', node_name=c['node_name'], role=c['role'])

@app.route('/inventory')
def inventory_page():
    c = _cfg.load()
    return render_template('inventory.html', node_name=c['node_name'], role=c['role'])

@app.route('/master')
def master_page():
    c = _cfg.load()
    return render_template('master.html', node_name=c['node_name'], role=c['role'])

# ─── API ROL ─────────────────────────────────────────────────────────────────

@app.route('/api/role', methods=['GET'])
def api_get_role():
    c = _cfg.load()
    return jsonify({
        "role":       c['role'],
        "node_name":  c['node_name'],
        "master_ip":  c.get('master_ip', ''),
        "can_write":  _can_write(),
        "is_authority": _is_authority(),
        "roles_available": list(ROLES.keys())[:3],  # solo admin/servidor/cliente al usuario
    })

@app.route('/api/role', methods=['POST'])
def api_set_role():
    data = request.get_json(force=True)
    new_role = data.get('role', '').lower()
    if new_role not in ROLES:
        abort(400, description=f"Rol inválido. Opciones: {', '.join(list(ROLES.keys())[:3])}")
    master_ip = data.get('master_ip', _cfg.get('master_ip', ''))
    _cfg.update({'role': new_role, 'master_ip': master_ip})
    # Si pasa a servidor/cliente, sincroniza BD del master
    synced = 0
    if not ROLES[new_role]['is_authority'] and master_ip:
        synced = _sync_from_master()
    return jsonify({
        "role":    new_role,
        "master_ip": master_ip,
        "synced_items": synced,
        "can_write": ROLES[new_role]['can_write'],
    })

@app.route('/api/sync', methods=['POST'])
def api_sync():
    """Fuerza sync de BD desde master."""
    if _is_authority():
        return jsonify({"error": "Este nodo ES el master, no sincroniza"}), 400
    synced = _sync_from_master()
    return jsonify({"synced_items": synced})

# ─── API INVENTARIO ──────────────────────────────────────────────────────────

@app.route('/api/items', methods=['GET'])
def api_get_items():
    category = request.args.get('category')
    if not _is_authority():
        try:
            path = '/api/items' + (f'?category={category}' if category else '')
            result = _proxy_to_master(path)
            if result is not None:
                resp = jsonify(result)
                resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                return resp
        except Exception:
            pass
    resp = jsonify(db.get_items(category))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

@app.route('/api/items/<sku>', methods=['GET'])
def api_get_item(sku):
    if not _is_authority():
        try:
            result = _proxy_to_master(f'/api/items/{sku}')
            if result is not None:
                resp = jsonify(result)
                resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                return resp
        except Exception:
            pass
    item = db.get_item(sku)
    if not item:
        abort(404, description="Item no encontrado")
    resp = jsonify(item)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

@app.route('/api/items', methods=['POST'])
def api_create_item():
    data = request.get_json(force=True)
    required = ('sku', 'name')
    for f in required:
        if not data.get(f):
            abort(400, description=f"Campo requerido: {f}")
    if not _can_write():
        try:
            result = _proxy_to_master('/api/items', method='POST', body=data)
            if result is not None:
                return jsonify(result), 201
        except Exception as e:
            abort(503, description=f"No se puede escribir: rol '{_role()}' requiere conexión al master")
    if db.get_item(data['sku']):
        abort(409, description="SKU ya existe")
    db.create_item(data)
    return jsonify(db.get_item(data['sku'])), 201

@app.route('/api/items/<sku>', methods=['PUT'])
def api_update_item(sku):
    data = request.get_json(force=True)
    if not _can_write():
        try:
            result = _proxy_to_master(f'/api/items/{sku}', method='PUT', body=data)
            if result is not None:
                return jsonify(result)
        except Exception:
            abort(503, description=f"No se puede escribir: rol '{_role()}' requiere conexión al master")
    if not db.get_item(sku):
        abort(404, description="Item no encontrado")
    db.update_item(sku, data)
    return jsonify(db.get_item(sku))

@app.route('/api/items/<sku>', methods=['DELETE'])
def api_delete_item(sku):
    if not _can_write():
        try:
            result = _proxy_to_master(f'/api/items/{sku}', method='DELETE')
            if result is not None:
                return jsonify(result)
        except Exception:
            abort(503, description=f"No se puede escribir: rol '{_role()}' requiere conexión al master")
    if not db.get_item(sku):
        abort(404, description="Item no encontrado")
    db.delete_item(sku)
    return jsonify({'deleted': sku})

# ─── API TRANSACCIONES ────────────────────────────────────────────────────────

@app.route('/api/transactions', methods=['GET'])
def api_transactions():
    limit = int(request.args.get('limit', 100))
    sku   = request.args.get('sku')
    node  = request.args.get('node')
    return jsonify(db.get_transactions(limit, sku, node))

@app.route('/api/transactions', methods=['POST'])
def api_create_transaction():
    data = request.get_json(force=True)
    required = ('message_id', 'origin_node', 'action', 'sku')
    for f in required:
        if not data.get(f):
            abort(400, description=f"Campo requerido: {f}")
    now = time.time()
    tx = {
        'message_id':        data['message_id'],
        'origin_node':       data['origin_node'],
        'action':            data['action'],
        'sku':               data['sku'],
        'quantity_delta':    data.get('quantity_delta', 1),
        'timestamp_created': data.get('timestamp_created', now),
        'timestamp_received': now,
        'latency_ms':        max(0, (now - data.get('timestamp_created', now)) * 1000),
        'payload':           str(data.get('payload', '')),
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
    metrics['can_write'] = _can_write()
    resp = jsonify(metrics)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

@app.route('/api/low-stock')
def api_low_stock():
    threshold = int(request.args.get('threshold', 10))
    return jsonify(db.get_low_stock(threshold))

@app.route('/api/network-topology')
def api_topology():
    metrics = db.get_metrics()
    return jsonify({
        'nodes': metrics['nodes'],
        'by_node': metrics['by_node'],
        'total_packets': metrics['total_transactions'],
    })

@app.route('/api/logs')
def api_logs():
    try:
        with open(app.config['LOG_FILE'], 'r') as f:
            lines = f.readlines()[-100:]
    except Exception:
        lines = []
    return jsonify({'logs': lines})

@app.route('/api/provisioned-nodes')
def api_provisioned_nodes():
    try:
        import provisioner
        return jsonify(provisioner.get_assigned_nodes())
    except Exception:
        return jsonify([])

# ─── ERROR HANDLERS ──────────────────────────────────────────────────────────

@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(409)
@app.errorhandler(503)
def handle_error(e):
    return jsonify({'error': str(e.description)}), e.code


if __name__ == '__main__':
    c = _cfg.load()
    print(f"Dashboard iniciado — {c['node_name']} rol={c['role']}")
    print("Acceso: http://localhost:5080")
    print("Inventario: http://localhost:5080/inventory")
    app.run(host='0.0.0.0', port=int(os.getenv('DASHBOARD_PORT', 5080)),
            debug=False, threaded=True)
