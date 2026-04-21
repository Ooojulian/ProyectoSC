#!/usr/bin/env python3
"""
Provisioner — solo corre en el nodo maestro.

Hace dos cosas:
  1. Anuncia presencia por UDP broadcast para que nodos nuevos lo encuentren.
  2. Escucha conexiones TCP entrantes de nodos nuevos:
       - Asigna nombre y rol
       - Envía ZIP con todo el código del proyecto
       - Envía config JSON personalizada para ese nodo
       - Envía dump de la DB (items + transacciones)
       - El nodo cliente lo descomprime y arranca solo

Protocolo TCP (framing simple):
  [4 bytes big-endian length][payload bytes]

Mensajes JSON de control:
  {"type": "hello",  "node_name": "Node-X", "ip": "..."}
  {"type": "assign", "node_name": "Node-2", "role": "replica", "bat0_ip": "..."}
  {"type": "file",   "name": "project.zip", "size": N}       → luego N bytes raw
  {"type": "dbdump", "name": "inventory.db", "size": N}      → luego N bytes raw
  {"type": "config", ...cfg dict...}
  {"type": "done"}
"""

import socket, threading, json, struct, zipfile, io, os, time, logging
from pathlib import Path
import node_config as cfg
import db as _db

LOG = logging.getLogger("Provisioner")
BASE = Path(__file__).parent

ROLE_SEQUENCE = ["replica", "sensor", "gateway", "replica"]  # round-robin para nuevos nodos
_assigned: list[dict] = []   # nodos ya provisionados
_lock = threading.Lock()

ANNOUNCE_MSG = b"PROYECTOSC_MASTER"


# ─── Utilidades de framing ───────────────────────────────────────────────────

def send_frame(sock: socket.socket, data: bytes):
    sock.sendall(struct.pack(">I", len(data)) + data)

def recv_frame(sock: socket.socket) -> bytes:
    raw = _recvn(sock, 4)
    if not raw:
        return b""
    n = struct.unpack(">I", raw)[0]
    return _recvn(sock, n)

def _recvn(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return b""
        buf += chunk
    return buf

def send_json(sock: socket.socket, obj: dict):
    send_frame(sock, json.dumps(obj).encode())

def recv_json(sock: socket.socket) -> dict:
    raw = recv_frame(sock)
    return json.loads(raw) if raw else {}


# ─── Crear ZIP del proyecto ───────────────────────────────────────────────────

def build_project_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for ext in ("*.py",):
            for f in BASE.glob(ext):
                zf.write(f, f.name)
        # web_dashboard
        for f in (BASE / "web_dashboard").rglob("*"):
            if f.is_file():
                zf.write(f, str(f.relative_to(BASE)))
        # scripts
        for f in (BASE / "scripts").glob("*.sh"):
            zf.write(f, str(f.relative_to(BASE)))
        # config env
        env_f = BASE / "config" / "default.env"
        if env_f.exists():
            zf.write(env_f, "config/default.env")
    return buf.getvalue()


def build_db_dump() -> bytes:
    db_path = Path(_db.DB_PATH)
    if db_path.exists():
        return db_path.read_bytes()
    return b""


# ─── Asignación de nodos ──────────────────────────────────────────────────────

def _next_assignment(hello: dict) -> dict:
    with _lock:
        idx    = len(_assigned)
        role   = ROLE_SEQUENCE[idx % len(ROLE_SEQUENCE)]
        num    = idx + 2          # maestro es Node-1, clientes empiezan en Node-2
        name   = f"Node-{num}"
        bat_ip = f"192.168.200.{100 + num}"
        record = {
            "node_name": name,
            "role":      role,
            "bat0_ip":   bat_ip,
            "ip":        hello.get("ip", ""),
            "connected_at": time.time(),
        }
        _assigned.append(record)
        LOG.info(f"Asignado {name} rol={role} ip={bat_ip}")
        return record


# ─── Manejador de conexión entrante ──────────────────────────────────────────

def _handle_client(conn: socket.socket, addr):
    LOG.info(f"Conexión entrante de {addr}")
    try:
        hello = recv_json(conn)
        if hello.get("type") != "hello":
            LOG.warning(f"Mensaje inesperado: {hello}")
            return

        assign = _next_assignment(hello)

        # 1. Enviar asignación
        send_json(conn, {"type": "assign", **assign})

        # 2. Enviar ZIP del proyecto
        LOG.info(f"Enviando código a {assign['node_name']}…")
        zdata = build_project_zip()
        send_json(conn, {"type": "file", "name": "project.zip", "size": len(zdata)})
        send_frame(conn, zdata)

        # 3. Enviar DB dump
        LOG.info(f"Enviando DB a {assign['node_name']}…")
        dbdata = build_db_dump()
        send_json(conn, {"type": "dbdump", "name": "inventory.db", "size": len(dbdata)})
        send_frame(conn, dbdata)

        # 4. Enviar config personalizada
        node_cfg = {
            **cfg.load(),
            "node_name":  assign["node_name"],
            "role":       assign["role"],
            "bat0_ip":    assign["bat0_ip"],
            "master_ip":  cfg.get("bat0_ip"),
        }
        send_json(conn, {"type": "config", **node_cfg})

        # 5. Done
        send_json(conn, {"type": "done"})
        LOG.info(f"Provisioning completo para {assign['node_name']}")

        # Confirmar que el cliente recibió todo
        ack = recv_json(conn)
        if ack.get("type") == "ack":
            LOG.info(f"{assign['node_name']} listo y ejecutando.")

    except Exception as e:
        LOG.error(f"Error provisionando {addr}: {e}")
    finally:
        conn.close()


# ─── UDP Announce ─────────────────────────────────────────────────────────────

def _announce_loop(interval=5):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    port = cfg.get("provision_port", 12346)
    LOG.info(f"Anunciando maestro en broadcast:{port} cada {interval}s")
    while True:
        try:
            payload = json.dumps({
                "type":      "master_announce",
                "master_ip": cfg.get("bat0_ip"),
                "port":      port,
                "node_name": cfg.get("node_name"),
            }).encode()
            sock.sendto(payload, ("255.255.255.255", port))
        except Exception as e:
            LOG.warning(f"Announce error: {e}")
        time.sleep(interval)


# ─── TCP Server ───────────────────────────────────────────────────────────────

def start_server():
    port = cfg.get("provision_port", 12346)
    srv  = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("", port))
    srv.listen(10)
    LOG.info(f"Provisioner TCP escuchando en :{port}")

    t_ann = threading.Thread(target=_announce_loop, daemon=True)
    t_ann.start()

    while True:
        try:
            conn, addr = srv.accept()
            t = threading.Thread(target=_handle_client, args=(conn, addr), daemon=True)
            t.start()
        except Exception as e:
            LOG.error(f"Accept error: {e}")


def get_assigned_nodes() -> list:
    with _lock:
        return list(_assigned)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
    start_server()
