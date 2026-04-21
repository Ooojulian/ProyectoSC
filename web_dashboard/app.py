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

app = Flask(__name__)
app.config['NODE_NAME'] = os.getenv('NODE_NAME', 'Node-1')
app.config['LOG_FILE']  = '/home/julian/ProyectoSC/logs/sensor.log'

db.init_db()

# ─── PÁGINAS ────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    return render_template('dashboard.html', node_name=app.config['NODE_NAME'])

@app.route('/inventory')
def inventory_page():
    return render_template('inventory.html', node_name=app.config['NODE_NAME'])

# ─── API INVENTARIO ──────────────────────────────────────────────────────────

@app.route('/api/items', methods=['GET'])
def api_get_items():
    category = request.args.get('category')
    return jsonify(db.get_items(category))

@app.route('/api/items/<sku>', methods=['GET'])
def api_get_item(sku):
    item = db.get_item(sku)
    if not item:
        abort(404, description="Item no encontrado")
    return jsonify(item)

@app.route('/api/items', methods=['POST'])
def api_create_item():
    data = request.get_json(force=True)
    required = ('sku', 'name')
    for f in required:
        if not data.get(f):
            abort(400, description=f"Campo requerido: {f}")
    if db.get_item(data['sku']):
        abort(409, description="SKU ya existe")
    db.create_item(data)
    return jsonify(db.get_item(data['sku'])), 201

@app.route('/api/items/<sku>', methods=['PUT'])
def api_update_item(sku):
    if not db.get_item(sku):
        abort(404, description="Item no encontrado")
    data = request.get_json(force=True)
    db.update_item(sku, data)
    return jsonify(db.get_item(sku))

@app.route('/api/items/<sku>', methods=['DELETE'])
def api_delete_item(sku):
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
    """Endpoint para recibir transacciones de otros nodos (sync manual)."""
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
        'latency_ms':        (now - data.get('timestamp_created', now)) * 1000,
        'payload':           str(data.get('payload', '')),
    }
    inserted = db.insert_transaction(tx)
    return jsonify({'inserted': inserted, 'message_id': tx['message_id']}), (201 if inserted else 200)

# ─── API MÉTRICAS / ESTADO ───────────────────────────────────────────────────

@app.route('/api/metrics')
def api_metrics():
    metrics = db.get_metrics()
    metrics['node_name'] = app.config['NODE_NAME']
    metrics['timestamp'] = time.time()
    metrics['status'] = 'online'
    return jsonify(metrics)

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

@app.route('/master')
def master_page():
    c = _cfg.load()
    return render_template('master.html', node_name=c['node_name'])

# ─── ERROR HANDLERS ──────────────────────────────────────────────────────────

@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(409)
def handle_error(e):
    return jsonify({'error': str(e.description)}), e.code


if __name__ == '__main__':
    print(f"Dashboard iniciado — {app.config['NODE_NAME']}")
    print("Acceso: http://localhost:5000")
    print("Admin inventario: http://localhost:5000/inventory")
    app.run(host='0.0.0.0', port=int(os.getenv('DASHBOARD_PORT', 5080)),
            debug=False, threaded=True)
