#!/usr/bin/env python3
"""
Configuración dinámica del nodo.
Persiste en JSON local. Leída por sensor, panel y provisioner.
"""
import json, os, threading
from pathlib import Path

CONFIG_PATH = Path(os.getenv("NODE_CONFIG_PATH", "/home/julian/ProyectoSC/data/node_config.json"))

DEFAULTS = {
    "node_name":          os.getenv("NODE_NAME", "Node-1"),
    "role":               os.getenv("NODE_ROLE", "master"),   # master | replica | sensor | gateway
    "master_ip":          os.getenv("MASTER_IP", ""),
    "bat0_ip":            os.getenv("BAT0_IP", "192.168.200.101"),
    "broadcast_ip":       "255.255.255.255",
    "broadcast_port":     12345,
    "provision_port":     12346,
    "dashboard_port":     5080,
    "control_port":       5001,
    # Comportamiento dinámico
    "collaboration_pct":  100,   # % de paquetes que reenvía a otros nodos (0-100)
    "online":             True,  # si False, el nodo no emite ni recibe
    "gen_rate":           float(os.getenv("GEN_RATE", "1.0")),
    "drop_prob":          float(os.getenv("DROP_PROB", "0.0")),
    "payload_size":       int(os.getenv("PAYLOAD_SIZE", "0")),
}

_lock = threading.Lock()


def load() -> dict:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                saved = json.load(f)
            cfg = {**DEFAULTS, **saved}
            return cfg
        except Exception:
            pass
    _save(DEFAULTS)
    return dict(DEFAULTS)


def _save(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def get(key, default=None):
    return load().get(key, default)


def set_value(key: str, value):
    with _lock:
        cfg = load()
        cfg[key] = value
        _save(cfg)
    return cfg


def update(patch: dict):
    with _lock:
        cfg = load()
        cfg.update(patch)
        _save(cfg)
    return cfg
