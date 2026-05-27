#!/usr/bin/env python3
"""
Lanzador P2P — arranca todos los servicios del nodo:
  - Sensor UDP (genera y recibe eventos de red)
  - Dashboard Flask  :5080

Uso: python3 node.py  (o a través de start.sh)
"""

import subprocess, sys, os, time, threading, logging, signal

BASE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
os.makedirs(os.path.join(BASE, "data"), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Node] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE, "logs", "node.log")),
        logging.StreamHandler(),
    ],
)
LOG = logging.getLogger("Node")

sys.path.insert(0, BASE)
import node_config as _cfg
import db as _db

_db.init_db()

# Aplicar vars de entorno al JSON — pisan cualquier valor residual del arranque anterior
_patch = {}
if os.getenv("NODE_NAME"):  _patch["node_name"] = os.getenv("NODE_NAME")
if os.getenv("BAT0_IP"):    _patch["bat0_ip"]   = os.getenv("BAT0_IP")
if os.getenv("NODE_ROLE"):  _patch["role"]       = os.getenv("NODE_ROLE")
if _patch:
    _cfg.update(_patch)

c = _cfg.load()
LOG.info(f"Nodo: {c['node_name']}  IP: {c['bat0_ip']}  Rol: {c['role']}")

SERVICES = [
    {
        "name": "Sensor",
        "cmd":  [sys.executable, os.path.join(BASE, "sensor_node.py")],
        "log":  "logs/sensor.log",
    },
    {
        "name": "Dashboard",
        "cmd":  [sys.executable, os.path.join(BASE, "web_dashboard", "app.py")],
        "log":  "logs/dashboard.log",
    },
]

_procs: list[dict] = []


def _free_port(port: int):
    try:
        subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
        time.sleep(1)
    except Exception:
        pass


def start_service(svc: dict) -> subprocess.Popen:
    log_path = os.path.join(BASE, svc["log"])
    c = _cfg.load()
    env = {**os.environ,
           "NODE_NAME": c["node_name"],
           "NODE_ROLE": c["role"],
           "BAT0_IP":   c["bat0_ip"]}
    LOG.info(f"Arrancando {svc['name']}…")
    with open(log_path, "a") as lf:
        proc = subprocess.Popen(
            svc["cmd"], env=env, cwd=BASE,
            stdout=lf, stderr=subprocess.STDOUT,
        )
    LOG.info(f"  {svc['name']} PID={proc.pid}")
    return proc


def _watchdog():
    _fail_counts: dict[str, int] = {}
    while True:
        time.sleep(5)
        for entry in _procs:
            proc = entry["proc"]
            if proc.poll() is not None:
                name = entry["name"]
                _fail_counts[name] = _fail_counts.get(name, 0) + 1
                backoff = min(30, _fail_counts[name] * 3)
                LOG.warning(f"{name} murió (rc={proc.returncode}). Esperando {backoff}s…")
                time.sleep(backoff)
                if name == "Dashboard":
                    _free_port(5080)
                entry["proc"] = start_service(entry["svc"])
                _fail_counts[name] = 0


def _stop_all(sig=None, frame=None):
    LOG.info("Deteniendo servicios…")
    for entry in _procs:
        try:
            entry["proc"].terminate()
        except Exception:
            pass
    time.sleep(1)
    for entry in _procs:
        try:
            entry["proc"].kill()
        except Exception:
            pass
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT,  _stop_all)
    signal.signal(signal.SIGTERM, _stop_all)

    for svc in SERVICES:
        time.sleep(0.3)
        proc = start_service(svc)
        _procs.append({"name": svc["name"], "svc": svc, "proc": proc})

    LOG.info("")
    LOG.info("Servicios corriendo:")
    LOG.info("  Dashboard → http://localhost:5080")
    LOG.info("Ctrl+C para detener.")

    threading.Thread(target=_watchdog, daemon=True).start()

    while True:
        time.sleep(10)
