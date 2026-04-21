#!/usr/bin/env python3
"""
Panel de Control del Nodo — puerto 5001
Permite configurar en tiempo real:
  - % colaboración (cuántos paquetes reenvía)
  - % envidia     (cuántos paquetes ignora de otros nodos)
  - online/offline (apagar/encender el nodo)
  - ver paquetes en tiempo real (de quién, a quién, tamaño, latencia)
  - mapa de comunicaciones
  - log de red en vivo
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, jsonify, request
import node_config as cfg
import db as _db
import time
import threading
from collections import deque

app = Flask(__name__, template_folder="web_dashboard/templates")

# Buffer de paquetes en tiempo real (compartido con sensor_node via módulo)
packet_log: deque = deque(maxlen=200)
_log_lock = threading.Lock()


def log_packet(direction: str, origin: str, dest: str, sku: str,
               action: str, size_bytes: int, latency_ms: float, dropped: bool = False):
    """Llamado desde sensor_node.py para registrar cada paquete."""
    with _log_lock:
        packet_log.append({
            "ts":         time.time(),
            "direction":  direction,   # "in" | "out"
            "origin":     origin,
            "dest":       dest,
            "sku":        sku,
            "action":     action,
            "size":       size_bytes,
            "latency_ms": round(latency_ms, 2),
            "dropped":    dropped,
        })


# ─── API ─────────────────────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def api_get_config():
    return jsonify(cfg.load())


@app.route("/api/config", methods=["POST"])
def api_set_config():
    data = request.get_json(force=True)
    allowed = {"collaboration_pct", "online",
                "gen_rate", "drop_prob", "payload_size"}
    patch = {k: v for k, v in data.items() if k in allowed}
    if not patch:
        return jsonify({"error": "Sin campos válidos"}), 400
    updated = cfg.update(patch)
    return jsonify(updated)


@app.route("/api/packets")
def api_packets():
    limit = int(request.args.get("limit", 50))
    with _log_lock:
        pkts = list(packet_log)[-limit:]
    return jsonify(list(reversed(pkts)))


@app.route("/api/comms-map")
def api_comms_map():
    """Retorna grafo de comunicaciones: quién habla con quién y cuántos paquetes."""
    rows = _db.get_transactions(limit=500)
    edges: dict[str, int] = {}
    my_name = cfg.get("node_name")
    for r in rows:
        key = f"{r['origin_node']}→{my_name}" if r["origin_node"] != my_name else f"{my_name}→broadcast"
        edges[key] = edges.get(key, 0) + 1
    nodes_seen = set()
    for r in rows:
        nodes_seen.add(r["origin_node"])
    nodes_seen.add(my_name)
    return jsonify({"edges": edges, "nodes": list(nodes_seen)})


@app.route("/api/node-status")
def api_node_status():
    c = cfg.load()
    metrics = _db.get_metrics()
    with _log_lock:
        recent = list(packet_log)[-20:]
    return jsonify({
        "node_name":        c["node_name"],
        "role":             c["role"],
        "online":           c["online"],
        "collaboration_pct": c["collaboration_pct"],
        "gen_rate":         c["gen_rate"],
        "drop_prob":        c["drop_prob"],
        "total_tx":         metrics["total_transactions"],
        "avg_latency":      metrics["avg_latency_ms"],
        "nodes_seen":       [n["name"] for n in metrics["nodes"]],
        "recent_packets":   recent,
    })


@app.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    cfg.set_value("online", False)
    return jsonify({"status": "offline"})


@app.route("/api/wakeup", methods=["POST"])
def api_wakeup():
    cfg.set_value("online", True)
    return jsonify({"status": "online"})


# ─── Página ──────────────────────────────────────────────────────────────────

@app.route("/")
def control_page():
    c = cfg.load()
    return render_template("control_panel.html",
                           node_name=c["node_name"],
                           role=c["role"])


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s [ControlPanel] %(levelname)s %(message)s")
    c = cfg.load()
    port = c.get("control_port", 5001)
    print(f"Panel de control: http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
