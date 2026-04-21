#!/usr/bin/env python3
"""
Bootstrap del nodo cliente.
Se ejecuta en el nodo nuevo ANTES de tener el código.
  python3 client_bootstrap.py <master_ip>   (o sin args → auto-descubre por UDP)

1. Escucha el anuncio UDP del maestro (o usa IP directa)
2. Conecta TCP al provisioner
3. Recibe y descomprime el proyecto
4. Recibe y restaura la DB
5. Aplica la config asignada
6. Arranca sensor_node.py + web_dashboard/app.py + control_panel.py
"""

import socket, json, struct, zipfile, io, os, sys, subprocess, time, logging

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [Bootstrap] %(levelname)s %(message)s")
LOG = logging.getLogger("Bootstrap")

INSTALL_DIR = os.path.expanduser("~/ProyectoSC")
PROVISION_PORT = 12346


# ─── Framing (mismo protocolo que provisioner.py) ────────────────────────────

def send_frame(sock, data: bytes):
    sock.sendall(struct.pack(">I", len(data)) + data)

def recv_frame(sock) -> bytes:
    raw = _recvn(sock, 4)
    if not raw: return b""
    n = struct.unpack(">I", raw)[0]
    return _recvn(sock, n)

def _recvn(sock, n) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk: return b""
        buf += chunk
    return buf

def send_json(sock, obj):
    send_frame(sock, json.dumps(obj).encode())

def recv_json(sock) -> dict:
    raw = recv_frame(sock)
    return json.loads(raw) if raw else {}


# ─── Descubrimiento del maestro ───────────────────────────────────────────────

def discover_master(timeout=30) -> tuple[str, int]:
    """Escucha broadcast UDP hasta encontrar el maestro."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", PROVISION_PORT))
    sock.settimeout(1.0)
    LOG.info(f"Buscando maestro en la red (timeout={timeout}s)…")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(1024)
            msg = json.loads(data.decode())
            if msg.get("type") == "master_announce":
                ip   = msg.get("master_ip") or addr[0]
                port = msg.get("port", PROVISION_PORT)
                LOG.info(f"Maestro encontrado: {ip}:{port}")
                sock.close()
                return ip, port
        except socket.timeout:
            LOG.info("Esperando anuncio del maestro…")
        except Exception:
            pass
    sock.close()
    raise TimeoutError("No se encontró el maestro en la red.")


# ─── Provisioning ─────────────────────────────────────────────────────────────

def run_bootstrap(master_ip: str, master_port: int = PROVISION_PORT):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)
    LOG.info(f"Conectando a maestro {master_ip}:{master_port}…")
    sock.connect((master_ip, master_port))

    # 1. Saludo
    my_ip = _get_my_ip()
    send_json(sock, {"type": "hello", "ip": my_ip})

    assign = {}

    while True:
        msg = recv_json(sock)
        mtype = msg.get("type")
        LOG.info(f"Mensaje recibido: {mtype}")

        if mtype == "assign":
            assign = msg
            LOG.info(f"Asignado como {assign['node_name']} rol={assign['role']}")

        elif mtype == "file":
            size  = msg["size"]
            fdata = recv_frame(sock)
            LOG.info(f"Recibiendo {msg['name']} ({size} bytes)…")
            _install_zip(fdata)

        elif mtype == "dbdump":
            size   = msg["size"]
            dbdata = recv_frame(sock)
            if dbdata:
                LOG.info(f"Restaurando DB ({size} bytes)…")
                _restore_db(dbdata)

        elif mtype == "config":
            cfg_data = {k: v for k, v in msg.items() if k != "type"}
            _write_config(cfg_data)

        elif mtype == "done":
            send_json(sock, {"type": "ack"})
            break

        else:
            LOG.warning(f"Tipo desconocido: {mtype}")

    sock.close()
    LOG.info("Provisioning completo. Arrancando nodo…")
    _launch_node(assign)


def _install_zip(data: bytes):
    os.makedirs(INSTALL_DIR, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(INSTALL_DIR)
    LOG.info(f"Código instalado en {INSTALL_DIR}")
    # Instalar dependencias
    req = os.path.join(INSTALL_DIR, "requirements.txt")
    if os.path.exists(req):
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", req,
                        "--quiet", "--break-system-packages"], check=False)
    else:
        subprocess.run([sys.executable, "-m", "pip", "install", "flask",
                        "--quiet", "--break-system-packages"], check=False)


def _restore_db(data: bytes):
    import db as _db
    db_path = _db.DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with open(db_path, "wb") as f:
        f.write(data)
    LOG.info(f"DB restaurada en {db_path}")


def _write_config(cfg_data: dict):
    sys.path.insert(0, INSTALL_DIR)
    import node_config as nc
    nc.update(cfg_data)
    LOG.info(f"Config guardada: {cfg_data.get('node_name')} rol={cfg_data.get('role')}")


def _launch_node(assign: dict):
    env = {
        **os.environ,
        "NODE_NAME": assign.get("node_name", "Node-2"),
        "NODE_ROLE": assign.get("role", "replica"),
        "BAT0_IP":   assign.get("bat0_ip", ""),
        "MASTER_IP": assign.get("master_ip", ""),
    }
    procs = [
        [sys.executable, os.path.join(INSTALL_DIR, "sensor_node.py")],
        [sys.executable, os.path.join(INSTALL_DIR, "web_dashboard", "app.py")],
        [sys.executable, os.path.join(INSTALL_DIR, "control_panel.py")],
    ]
    for cmd in procs:
        LOG.info(f"Arrancando: {' '.join(cmd)}")
        subprocess.Popen(cmd, env=env, cwd=INSTALL_DIR)
    LOG.info("Todos los servicios lanzados.")


def _get_my_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        master_ip = sys.argv[1]
        port = int(sys.argv[2]) if len(sys.argv) > 2 else PROVISION_PORT
    else:
        master_ip, port = discover_master(timeout=60)
    run_bootstrap(master_ip, port)
