#!/usr/bin/env python3
"""
Configuración dinámica del nodo.
Persiste en JSON local. Leída por sensor, panel y dashboard.
"""
import json, os, threading
from pathlib import Path

CONFIG_PATH = Path(os.getenv("NODE_CONFIG_PATH", os.path.join(os.path.expanduser("~"), "ProyectoSC", "data", "node_config.json")))

DEFAULTS = {
    "node_name":          os.getenv("NODE_NAME", "Nodo"),
    "role":               os.getenv("NODE_ROLE", "peer"),
    "bat0_ip":            os.getenv("BAT0_IP", ""),
    "broadcast_ip":       "255.255.255.255",
    "broadcast_port":     12345,
    "dashboard_port":     5080,
    "collaboration_pct":  100,
    "envy_pct":           0,
    "online":             True,
    "gen_rate":           float(os.getenv("GEN_RATE", "1.0")),
    "drop_prob":          float(os.getenv("DROP_PROB", "0.0")),
    "payload_size":       int(os.getenv("PAYLOAD_SIZE", "0")),
}

_lock = threading.Lock()


def _load_unsafe() -> dict:
    """Lee config sin adquirir lock — solo llamar con lock ya tomado."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                saved = json.load(f)
            return {**DEFAULTS, **saved}
        except Exception:
            pass
    _save_unsafe(DEFAULTS)
    return dict(DEFAULTS)


def _save_unsafe(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def load() -> dict:
    with _lock:
        return _load_unsafe()


def get(key, default=None):
    return load().get(key, default)


def set_value(key: str, value):
    with _lock:
        cfg = _load_unsafe()
        cfg[key] = value
        _save_unsafe(cfg)
    return cfg


def update(patch: dict):
    with _lock:
        cfg = _load_unsafe()
        cfg.update(patch)
        _save_unsafe(cfg)
    return cfg
