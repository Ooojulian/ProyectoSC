#!/usr/bin/env python3
"""
Database layer - SQLite local por nodo.
"""

import sqlite3
import os
import threading
import time
from pathlib import Path

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.expanduser("~"), "ProyectoSC", "data", "inventory.db"))
_local = threading.local()
_db_lock = threading.Lock()


def get_conn():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10.0)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _local.conn.execute("PRAGMA busy_timeout=10000")
    return _local.conn


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    # timeout largo para sobrevivir si otro proceso tiene la DB
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # WAL permite lecturas concurrentes y reduce contención
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=20000")

    # Usar execute individual en lugar de executescript para evitar
    # el COMMIT implícito que falla bajo lock de otro proceso
    stmts = [
        """CREATE TABLE IF NOT EXISTS transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id      TEXT    NOT NULL UNIQUE,
            origin_node     TEXT    NOT NULL,
            action          TEXT    NOT NULL,
            sku             TEXT    NOT NULL,
            quantity_delta  INTEGER NOT NULL DEFAULT 0,
            timestamp_created REAL  NOT NULL,
            timestamp_received REAL NOT NULL DEFAULT (strftime('%s','now')),
            latency_ms      REAL    NOT NULL DEFAULT 0,
            payload         TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS nodes (
            name        TEXT PRIMARY KEY,
            last_seen   REAL NOT NULL DEFAULT (strftime('%s','now')),
            packets_sent    INTEGER NOT NULL DEFAULT 0,
            packets_received INTEGER NOT NULL DEFAULT 0,
            role        TEXT NOT NULL DEFAULT 'peer',
            bat0_ip     TEXT NOT NULL DEFAULT ''
        )""",
        """CREATE TABLE IF NOT EXISTS chat_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_id      TEXT    NOT NULL UNIQUE,
            from_node   TEXT    NOT NULL,
            to_node     TEXT    NOT NULL DEFAULT 'all',
            body        TEXT    NOT NULL,
            ts          REAL    NOT NULL DEFAULT (strftime('%s','now'))
        )""",
        "CREATE INDEX IF NOT EXISTS idx_tx_node ON transactions(origin_node)",
        "CREATE INDEX IF NOT EXISTS idx_tx_ts   ON transactions(timestamp_created)",
        "CREATE INDEX IF NOT EXISTS idx_chat_ts ON chat_messages(ts)",
    ]
    for stmt in stmts:
        conn.execute(stmt)
    conn.commit()

    # Migraciones para DBs antiguas
    for migration in [
        "ALTER TABLE nodes ADD COLUMN role TEXT NOT NULL DEFAULT 'peer'",
        "ALTER TABLE nodes ADD COLUMN bat0_ip TEXT NOT NULL DEFAULT ''",
    ]:
        try:
            conn.execute(migration)
            conn.commit()
        except sqlite3.OperationalError:
            pass
    conn.close()
    init_game_table()



def insert_transaction(tx: dict) -> bool:
    """Inserta transacción. Retorna False si duplicado."""
    with _db_lock:
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
            node_role = tx.get("node_role", "peer")
            conn.execute(
                """INSERT INTO nodes(name, last_seen, packets_received, role)
                   VALUES(?,?,1,?)
                   ON CONFLICT(name) DO UPDATE SET
                     last_seen=excluded.last_seen,
                     packets_received=packets_received+1,
                     role=excluded.role""",
                (tx["origin_node"], tx["timestamp_received"], node_role)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


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


def upsert_node_ip(name: str, bat0_ip: str, role: str = None):
    """Registra o actualiza la IP bat0 de un nodo."""
    with _db_lock:
        conn = get_conn()
        if role:
            conn.execute(
                """INSERT INTO nodes(name, last_seen, bat0_ip, role)
                   VALUES(?,?,?,?)
                   ON CONFLICT(name) DO UPDATE SET
                     last_seen=excluded.last_seen,
                     bat0_ip=excluded.bat0_ip,
                     role=excluded.role""",
                (name, time.time(), bat0_ip, role)
            )
        else:
            conn.execute(
                """INSERT INTO nodes(name, last_seen, bat0_ip)
                   VALUES(?,?,?)
                   ON CONFLICT(name) DO UPDATE SET
                     last_seen=excluded.last_seen,
                     bat0_ip=excluded.bat0_ip""",
                (name, time.time(), bat0_ip)
            )
        conn.commit()


def insert_chat(msg_id: str, from_node: str, to_node: str, body: str) -> bool:
    """Guarda un mensaje de chat. Retorna False si duplicado."""
    with _db_lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO chat_messages(msg_id,from_node,to_node,body,ts) VALUES(?,?,?,?,?)",
                (msg_id, from_node, to_node, body, time.time())
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def get_chat(since: float = 0, limit: int = 100) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM chat_messages WHERE ts>? ORDER BY ts ASC LIMIT ?",
        (since, limit)
    ).fetchall()
    return [dict(r) for r in rows]


def get_known_nodes() -> list[dict]:
    """Retorna todos los nodos conocidos con su IP y rol."""
    conn = get_conn()
    return [dict(r) for r in conn.execute(
        "SELECT name, bat0_ip, role, last_seen FROM nodes ORDER BY name"
    ).fetchall()]


# ─── GAME ──────────────────────────────────────────────────────────────────────

def init_game_table():
    with _db_lock:
        conn = get_conn()
        conn.execute("""CREATE TABLE IF NOT EXISTS game_state (
            game_id   TEXT PRIMARY KEY,
            state     TEXT NOT NULL,
            updated   REAL NOT NULL DEFAULT (strftime('%s','now'))
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_game_updated ON game_state(updated DESC)")
        conn.commit()


def upsert_game(game_id: str, state: dict):
    import json as _j
    with _db_lock:
        conn = get_conn()
        conn.execute(
            """INSERT INTO game_state(game_id, state, updated) VALUES(?,?,?)
               ON CONFLICT(game_id) DO UPDATE SET state=excluded.state, updated=excluded.updated""",
            (game_id, _j.dumps(state), time.time())
        )
        conn.commit()


def get_game(game_id: str) -> dict | None:
    import json as _j
    conn = get_conn()
    row = conn.execute("SELECT state FROM game_state WHERE game_id=?", (game_id,)).fetchone()
    return _j.loads(row[0]) if row else None


def get_active_game() -> dict | None:
    import json as _j
    conn = get_conn()
    row = conn.execute(
        "SELECT state FROM game_state ORDER BY updated DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    s = _j.loads(row[0])
    # Partida activa = no terminada hace más de 2 minutos
    if s.get('phase') == 'finished' and time.time() - s.get('finished_at', 0) > 120:
        return None
    return s


def clear_old_games():
    """Elimina todas las partidas anteriores — llamado al crear una nueva."""
    with _db_lock:
        conn = get_conn()
        conn.execute("DELETE FROM game_state")
        conn.commit()


