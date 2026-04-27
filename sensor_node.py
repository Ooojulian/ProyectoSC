#!/usr/bin/env python3
"""
Nodo de Red Mesh Descentralizada — Sensor Distribuido
Lee configuración dinámica de node_config.py en cada ciclo.
Reporta cada paquete al control_panel para visualización en tiempo real.
"""

import socket, threading, json, time, uuid, random, os, sys, logging
from pathlib import Path
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db as _db
import node_config as _cfg
try:
    import control_panel as _cp
    _HAS_CP = True
except ImportError:
    _HAS_CP = False

_BASE = Path(os.path.dirname(os.path.abspath(__file__)))
(_BASE / "logs").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(str(_BASE / "logs" / "sensor.log")),
        logging.StreamHandler(),
    ],
)

SKUS = ["CAM-001","CAM-002","CAM-003","CAM-004","CAM-005",
        "ACC-001","ACC-002","ACC-003","CAL-001","CAL-002"]


def _cfg_now() -> dict:
    return _cfg.load()


def _log_pkt(direction, origin, dest, sku, action, size, latency, dropped=False):
    if _HAS_CP:
        _cp.log_packet(direction, origin, dest, sku, action, size, latency, dropped)


class SensorNode:
    def __init__(self):
        c = _cfg_now()
        self.node_id = str(uuid.uuid4())[:8]
        self.logger  = logging.getLogger(c["node_name"])
        self.running = True
        self.stats   = {
            "sent": 0, "received": 0, "dropped": 0,
            "duplicates": 0, "bytes_out": 0,
            "latencies": deque(maxlen=100),
        }
        self._lock = threading.Lock()
        _db.init_db()
        self.logger.info(f"Nodo iniciado — ID:{self.node_id} nombre:{c['node_name']} rol:{c['role']}")

    # ── Generar evento ────────────────────────────────────────────────────

    def _gen_event(self) -> dict:
        c = _cfg_now()
        return {
            "message_id":       str(uuid.uuid4()),
            "origin_node":      c["node_name"],
            "origin_id":        self.node_id,
            "timestamp_created": time.time(),
            "action":           random.choice(["add","remove","add","check"]),
            "sku":              random.choice(SKUS),
            "quantity_delta":   random.randint(1, 5),
            "sensor_reading":   random.randint(0, 100),
            **({"_pad": "x" * c["payload_size"]} if c.get("payload_size", 0) > 0 else {}),
        }

    # ── Broadcast UDP ─────────────────────────────────────────────────────

    def _broadcast(self, payload: str, c: dict):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind((c["bat0_ip"], 0))
            raw = payload.encode()
            sock.sendto(raw, (c["broadcast_ip"], c["broadcast_port"]))
            sock.close()
            with self._lock:
                self.stats["sent"]      += 1
                self.stats["bytes_out"] += len(raw)
        except Exception as e:
            self.logger.error(f"Broadcast error: {e}")

    # ── Recepción ─────────────────────────────────────────────────────────

    def _receive_loop(self):
        c    = _cfg_now()
        port = c["broadcast_port"]
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1.0)
        sock.bind(("", port))
        self.logger.info(f"Escuchando UDP :{port}")
        while self.running:
            try:
                data, _ = sock.recvfrom(8192)
                self._handle(data)
            except socket.timeout:
                continue
            except Exception as e:
                self.logger.error(f"Recv error: {e}")
        sock.close()

    def _handle(self, raw: bytes):
        c = _cfg_now()
        # Nodo offline → descarta todo
        if not c.get("online", True):
            return
        try:
            event = json.loads(raw.decode())
        except Exception:
            return

        msg_id  = event.get("message_id", "")
        origin  = event.get("origin_node", "?")
        sku     = event.get("sku", "?")
        action  = event.get("action", "?")
        size    = len(raw)
        my_name = c["node_name"]

        # Drop prob (interferencia)
        if random.random() < c.get("drop_prob", 0.0):
            with self._lock:
                self.stats["dropped"] += 1
            _log_pkt("in", origin, my_name, sku, action, size, 0, dropped=True)
            return

        now     = time.time()
        latency = max(0, (now - event.get("timestamp_created", now)) * 1000)

        tx = {
            "message_id":         msg_id,
            "origin_node":        origin,
            "action":             action,
            "sku":                sku,
            "quantity_delta":     event.get("quantity_delta", 1),
            "timestamp_created":  event.get("timestamp_created", now),
            "timestamp_received": now,
            "latency_ms":         latency,
            "payload":            str(event.get("sensor_reading", "")),
        }

        try:
            inserted = _db.insert_transaction(tx)
        except Exception as e:
            self.logger.debug(f"DB insert failed: {e}")
            return

        if inserted:
            with self._lock:
                self.stats["received"] += 1
                self.stats["latencies"].append(latency)
            _log_pkt("in", origin, my_name, sku, action, size, latency)
            self.logger.info(f"[{origin}] {action} {sku} Δ{tx['quantity_delta']} {latency:.1f}ms")

            # Colaboración: reenviar a la red según collaboration_pct
            collab = c.get("collaboration_pct", 100)
            if origin != my_name and random.randint(0, 99) < collab:
                self._broadcast(raw.decode(), c)
                _log_pkt("out", my_name, "broadcast", sku, action, size, 0)

    # ── Emisor ────────────────────────────────────────────────────────────

    def _emitter_loop(self):
        self.logger.info("Emisor iniciado")
        while self.running:
            c = _cfg_now()
            if not c.get("online", True):
                time.sleep(1)
                continue

            rate     = c.get("gen_rate", 1.0)
            interval = 1.0 / rate if rate > 0 else 60

            try:
                event   = self._gen_event()
                payload = json.dumps(event)
                self._broadcast(payload, c)
                _log_pkt("out", c["node_name"], "broadcast",
                         event["sku"], event["action"], len(payload.encode()), 0)

                # Persistir propio evento
                now = time.time()
                _db.insert_transaction({
                    "message_id":         event["message_id"],
                    "origin_node":        event["origin_node"],
                    "action":             event["action"],
                    "sku":                event["sku"],
                    "quantity_delta":     event["quantity_delta"],
                    "timestamp_created":  event["timestamp_created"],
                    "timestamp_received": now,
                    "latency_ms":         0.0,
                    "payload":            str(event.get("sensor_reading", "")),
                })
            except Exception as e:
                if "database is locked" in str(e):
                    self.logger.debug(f"Emitter DB busy: {e}")
                else:
                    self.logger.error(f"Emitter error: {e}")

            jitter = interval * 0.1
            time.sleep(interval + random.uniform(-jitter, jitter))

    # ── Métricas ──────────────────────────────────────────────────────────

    def metrics(self) -> dict:
        with self._lock:
            lats = list(self.stats["latencies"])
        avg = sum(lats) / len(lats) if lats else 0
        c   = _cfg_now()
        lam = c.get("gen_rate", 1.0)
        mu  = 1000 / avg if avg > 0 else 1000
        rho = min(lam / mu, 0.99)
        lq  = rho**2 / (1 - rho)
        wq  = lq / lam if lam > 0 else 0
        return {
            "node_name":   c["node_name"],
            "node_id":     self.node_id,
            "sent":        self.stats["sent"],
            "received":    self.stats["received"],
            "dropped":     self.stats["dropped"],
            "duplicates":  self.stats["duplicates"],
            "avg_latency": round(avg, 2),
            "rho":         round(rho, 4),
            "lq":          round(lq, 4),
            "wq":          round(wq, 4),
        }

    # ── Main ──────────────────────────────────────────────────────────────

    def start(self):
        tr = threading.Thread(target=self._receive_loop, daemon=True)
        te = threading.Thread(target=self._emitter_loop, daemon=True)
        tr.start(); te.start()
        self.logger.info("Nodo activo. Ctrl+C para detener.")
        try:
            while self.running:
                time.sleep(10)
                m = self.metrics()
                self.logger.info(
                    f"sent={m['sent']} recv={m['received']} "
                    f"drop={m['dropped']} lat={m['avg_latency']}ms rho={m['rho']}"
                )
        except KeyboardInterrupt:
            self.logger.info("Deteniendo…")
            self.running = False


if __name__ == "__main__":
    SensorNode().start()
