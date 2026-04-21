#!/usr/bin/env python3
"""
Nodo Maestro — arranca todos los servicios en tu PC:
  1. Provisioner TCP (espera y configura nodos nuevos)
  2. Sensor UDP (genera y recibe eventos)
  3. Dashboard Flask  :5000
  4. Panel de Control :5001

Uso: python3 master_node.py
"""

import subprocess, sys, os, time, threading, logging, signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Master] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "master.log")),
        logging.StreamHandler(),
    ],
)
LOG = logging.getLogger("Master")
BASE = os.path.dirname(os.path.abspath(__file__))

os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
os.makedirs(os.path.join(BASE, "data"), exist_ok=True)

import sys
sys.path.insert(0, BASE)
import node_config as _cfg
import db as _db

# Asegurar config maestra
_cfg.update({
    "node_name":        os.getenv("NODE_NAME", "Node-1"),
    "role":             "master",
    "bat0_ip":          os.getenv("BAT0_IP", "192.168.200.101"),
    "collaboration_pct": 100,
    "envy_pct":         0,
    "online":           True,
})
_db.init_db()

SERVICES = [
    {
        "name": "Provisioner",
        "cmd":  [sys.executable, os.path.join(BASE, "provisioner.py")],
        "log":  "logs/provisioner.log",
    },
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
    {
        "name": "ControlPanel",
        "cmd":  [sys.executable, os.path.join(BASE, "control_panel.py")],
        "log":  "logs/control_panel.log",
    },
]

_procs: list[dict] = []


def start_service(svc: dict) -> subprocess.Popen:
    log_path = os.path.join(BASE, svc["log"])
    env = {**os.environ, "NODE_NAME": _cfg.get("node_name", "Node-1"), "NODE_ROLE": "master"}
    LOG.info(f"Arrancando {svc['name']}…")
    with open(log_path, "a") as lf:
        proc = subprocess.Popen(
            svc["cmd"], env=env, cwd=BASE,
            stdout=lf, stderr=subprocess.STDOUT,
        )
    LOG.info(f"  {svc['name']} PID={proc.pid}")
    return proc


def _free_port(port: int):
    """Mata cualquier proceso que tenga el puerto ocupado."""
    import subprocess
    try:
        subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
        time.sleep(1)
    except Exception:
        pass

def watchdog():
    """Reinicia servicios que mueran inesperadamente."""
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
                # Liberar puertos según servicio
                port_map = {"Dashboard": 5000, "ControlPanel": 5001, "Provisioner": 12346}
                if name in port_map:
                    _free_port(port_map[name])
                entry["proc"] = start_service(entry["svc"])
                _fail_counts[name] = 0  # reset tras arranque exitoso


def stop_all(sig=None, frame=None):
    LOG.info("Deteniendo todos los servicios…")
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
    LOG.info("Todo detenido.")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT,  stop_all)
    signal.signal(signal.SIGTERM, stop_all)

    LOG.info("=" * 60)
    LOG.info("NODO MAESTRO iniciando")
    LOG.info(f"Nombre: {_cfg.get('node_name')}  IP: {_cfg.get('bat0_ip')}")
    LOG.info("=" * 60)

    for svc in SERVICES:
        time.sleep(0.5)  # pequeño delay entre arranques
        proc = start_service(svc)
        _procs.append({"name": svc["name"], "svc": svc, "proc": proc})

    time.sleep(2)
    LOG.info("")
    LOG.info("✅ Todos los servicios corriendo:")
    LOG.info("   Dashboard    → http://localhost:5000")
    LOG.info("   Inventario   → http://localhost:5000/inventory")
    LOG.info("   Panel Control→ http://localhost:5001")
    LOG.info("   Provisioner  → TCP :12346  (espera nodos nuevos)")
    LOG.info("")
    LOG.info("Presiona Ctrl+C para detener todo.")

    wd = threading.Thread(target=watchdog, daemon=True)
    wd.start()

    # Mantener vivo
    while True:
        time.sleep(10)
        alive = [e["name"] for e in _procs if e["proc"].poll() is None]
        LOG.debug(f"Vivos: {alive}")
