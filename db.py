#!/usr/bin/env python3
"""
Database layer - SQLite local por nodo
Maneja inventario + transacciones + sync log
"""

import sqlite3
import os
import threading
from pathlib import Path

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.expanduser("~"), "ProyectoSC", "data", "inventory.db"))
_local = threading.local()


def get_conn():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sku         TEXT    NOT NULL UNIQUE,
            name        TEXT    NOT NULL,
            category    TEXT    NOT NULL DEFAULT 'general',
            quantity    INTEGER NOT NULL DEFAULT 0,
            price       REAL    NOT NULL DEFAULT 0.0,
            description TEXT,
            updated_at  REAL    NOT NULL DEFAULT (unixepoch('now','subsec'))
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id      TEXT    NOT NULL UNIQUE,
            origin_node     TEXT    NOT NULL,
            action          TEXT    NOT NULL,
            sku             TEXT    NOT NULL,
            quantity_delta  INTEGER NOT NULL DEFAULT 0,
            timestamp_created REAL  NOT NULL,
            timestamp_received REAL NOT NULL DEFAULT (unixepoch('now','subsec')),
            latency_ms      REAL    NOT NULL DEFAULT 0,
            payload         TEXT
        );

        CREATE TABLE IF NOT EXISTS nodes (
            name        TEXT PRIMARY KEY,
            last_seen   REAL NOT NULL DEFAULT (unixepoch('now','subsec')),
            packets_sent    INTEGER NOT NULL DEFAULT 0,
            packets_received INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_tx_sku    ON transactions(sku);
        CREATE INDEX IF NOT EXISTS idx_tx_node   ON transactions(origin_node);
        CREATE INDEX IF NOT EXISTS idx_tx_ts     ON transactions(timestamp_created);
        CREATE INDEX IF NOT EXISTS idx_items_cat ON items(category);
    """)

    # Seed catálogo si vacío
    if conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0:
        catalog = [
            ("CAM-001", "Chaqueta Vintage", "ropa", 50, 120000),
            ("CAM-002", "Pantalón Clásico", "ropa", 30, 85000),
            ("CAM-003", "Camiseta Básica", "ropa", 100, 35000),
            ("ACC-001", "Bolso Cuero", "accesorios", 20, 200000),
            ("ACC-002", "Cinturón Café", "accesorios", 40, 45000),
            ("CAL-001", "Tenis Deportivos", "calzado", 25, 180000),
            ("CAL-002", "Botas Casuales", "calzado", 15, 250000),
            ("CAM-004", "Vestido Floral", "ropa", 35, 95000),
            ("ACC-003", "Gorra Negra", "accesorios", 60, 28000),
            ("CAM-005", "Hoodie Oversize", "ropa", 45, 110000),
        ]
        conn.executemany(
            "INSERT INTO items (sku, name, category, quantity, price) VALUES (?,?,?,?,?)",
            catalog
        )
    conn.commit()
    conn.close()


def tx_exists(message_id: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM transactions WHERE message_id=?", (message_id,)
    ).fetchone()
    return row is not None


def insert_transaction(tx: dict) -> bool:
    """Inserta transacción y actualiza stock. Retorna False si duplicado."""
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO transactions
               (message_id, origin_node, action, sku, quantity_delta,
                timestamp_created, timestamp_received, latency_ms, payload)
               VALUES (:message_id,:origin_node,:action,:sku,:quantity_delta,
                       :timestamp_created,:timestamp_received,:latency_ms,:payload)""",
            tx
        )
        # Actualizar stock
        delta = tx.get("quantity_delta", 0)
        if tx["action"] == "add":
            conn.execute(
                "UPDATE items SET quantity=quantity+?, updated_at=unixepoch('now','subsec') WHERE sku=?",
                (abs(delta), tx["sku"])
            )
        elif tx["action"] == "remove":
            conn.execute(
                "UPDATE items SET quantity=MAX(0,quantity-?), updated_at=unixepoch('now','subsec') WHERE sku=?",
                (abs(delta), tx["sku"])
            )
        # Upsert nodo
        conn.execute(
            """INSERT INTO nodes(name, last_seen, packets_received)
               VALUES(?,unixepoch('now','subsec'),1)
               ON CONFLICT(name) DO UPDATE SET
                 last_seen=excluded.last_seen,
                 packets_received=packets_received+1""",
            (tx["origin_node"],)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # duplicate


def get_items(category=None):
    conn = get_conn()
    if category:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM items WHERE category=? ORDER BY name", (category,)
        ).fetchall()]
    return [dict(r) for r in conn.execute(
        "SELECT * FROM items ORDER BY category, name"
    ).fetchall()]


def get_item(sku: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM items WHERE sku=?", (sku,)).fetchone()
    return dict(row) if row else None


def create_item(data: dict):
    conn = get_conn()
    conn.execute(
        "INSERT INTO items (sku,name,category,quantity,price,description) VALUES (?,?,?,?,?,?)",
        (data["sku"], data["name"], data.get("category","general"),
         data.get("quantity",0), data.get("price",0), data.get("description",""))
    )
    conn.commit()


def update_item(sku: str, data: dict):
    conn = get_conn()
    fields = {k: v for k, v in data.items() if k in ("name","category","quantity","price","description")}
    if not fields:
        return
    set_clause = ", ".join(f"{k}=?" for k in fields)
    set_clause += ", updated_at=unixepoch('now','subsec')"
    conn.execute(
        f"UPDATE items SET {set_clause} WHERE sku=?",
        (*fields.values(), sku)
    )
    conn.commit()


def delete_item(sku: str):
    conn = get_conn()
    conn.execute("DELETE FROM items WHERE sku=?", (sku,))
    conn.commit()


def get_transactions(limit=100, sku=None, node=None):
    conn = get_conn()
    q = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if sku:
        q += " AND sku=?"; params.append(sku)
    if node:
        q += " AND origin_node=?"; params.append(node)
    q += " ORDER BY timestamp_created DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(q, params).fetchall()]


def get_metrics():
    conn = get_conn()
    total_tx = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    avg_lat  = conn.execute("SELECT AVG(latency_ms) FROM transactions").fetchone()[0] or 0
    max_lat  = conn.execute("SELECT MAX(latency_ms) FROM transactions").fetchone()[0] or 0
    nodes    = conn.execute("SELECT * FROM nodes ORDER BY last_seen DESC").fetchall()
    by_node  = conn.execute(
        "SELECT origin_node, COUNT(*) as cnt FROM transactions GROUP BY origin_node"
    ).fetchall()
    by_action = conn.execute(
        "SELECT action, COUNT(*) as cnt FROM transactions GROUP BY action"
    ).fetchall()
    return {
        "total_transactions": total_tx,
        "avg_latency_ms": round(avg_lat, 2),
        "max_latency_ms": round(max_lat, 2),
        "nodes": [dict(n) for n in nodes],
        "by_node": {r["origin_node"]: r["cnt"] for r in by_node},
        "by_action": {r["action"]: r["cnt"] for r in by_action},
    }


def get_low_stock(threshold=10):
    conn = get_conn()
    return [dict(r) for r in conn.execute(
        "SELECT * FROM items WHERE quantity <= ? ORDER BY quantity", (threshold,)
    ).fetchall()]
