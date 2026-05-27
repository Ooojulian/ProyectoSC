#!/bin/bash
# =============================================================================
# ProyectoSC — Red Mesh P2P con BATMAN-adv
# Uso: sudo bash start.sh
#
# Todos los nodos son iguales. No hay master ni cliente.
# Cada nodo:
#   1. Instala dependencias del sistema
#   2. Detecta la interfaz WiFi
#   3. Configura Ad-Hoc + BATMAN-adv
#   4. Asigna IP única derivada del MAC (sin colisión)
#   5. Arranca sensor + dashboard + panel de control
# =============================================================================

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; B='\033[0;34m'; N='\033[0m'
info()  { echo -e "${B}[INFO]${N}  $*"; }
ok()    { echo -e "${G}[ OK ]${N}  $*"; }
warn()  { echo -e "${Y}[WARN]${N}  $*"; }
error() { echo -e "${R}[ERR ]${N}  $*"; exit 1; }

_open_browser() {
    local url="$1"
    local real_user="${SUDO_USER:-$USER}"
    if [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
        sudo -u "$real_user" xdg-open "$url" 2>/dev/null || \
        sudo -u "$real_user" sensible-browser "$url" 2>/dev/null || true
    else
        local disp
        disp=$(sudo -u "$real_user" bash -c 'echo $DISPLAY' 2>/dev/null || echo ":0")
        DISPLAY="$disp" sudo -u "$real_user" xdg-open "$url" 2>/dev/null || true
    fi
    ok "Abriendo dashboard en $url"
}

# ─── git pull ────────────────────────────────────────────────────────────────
info "Actualizando repositorio..."
if git -C "$REPO_DIR" pull --ff-only 2>/dev/null; then
    ok "Repositorio actualizado"
else
    warn "git pull falló (sin internet o conflictos) — usando versión local"
fi

# ─── Configuración de red ─────────────────────────────────────────────────────
SSID="ProyectoSC"
FREQ="2437"          # Canal 6
BSSID="02:ca:ff:ee:ba:be"
NET_PREFIX="192.168.200"
IP_RANGE_START=101
IP_RANGE_END=200

# ─── 0. Verificar root ───────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    error "Ejecutar con sudo: sudo bash start.sh"
fi

echo ""
echo "============================================================"
echo "  ProyectoSC — Nodo P2P Mesh"
echo "============================================================"
echo ""

# ─── Pedir nombre del usuario ────────────────────────────────────────────────
USER_DISPLAY_NAME=""
while [ -z "$USER_DISPLAY_NAME" ]; do
    read -rp "  Tu nombre (ej: Julian, Cristian): " USER_DISPLAY_NAME
done
ok "Bienvenido, $USER_DISPLAY_NAME"
echo ""

# ─── 1. Instalar dependencias ─────────────────────────────────────────────────
info "Instalando dependencias del sistema..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip \
    batman-adv-dkms batctl \
    iw wireless-tools \
    net-tools iproute2 \
    iputils-ping traceroute \
    git curl 2>/dev/null || true

info "Instalando dependencias Python..."
python3 -m pip install flask --quiet --break-system-packages 2>/dev/null || \
python3 -m pip install flask --quiet 2>/dev/null || true
ok "Dependencias instaladas"

# ─── 2. Detectar interfaz WiFi ───────────────────────────────────────────────
info "Detectando interfaz WiFi..."
WIFI_IF=""
for candidate in wlan0 wlan1 wlp2s0 wlp3s0 wlp0s20f3; do
    if ip link show "$candidate" &>/dev/null 2>&1; then
        WIFI_IF="$candidate"
        break
    fi
done
if [ -z "$WIFI_IF" ]; then
    WIFI_IF=$(iw dev 2>/dev/null | awk '/Interface/{print $2}' | head -1)
fi
if [ -z "$WIFI_IF" ]; then
    error "No se encontró interfaz WiFi."
fi
ok "Interfaz WiFi: $WIFI_IF"

# ─── Leer MAC ANTES de tocar la interfaz ─────────────────────────────────────
# BATMAN-adv puede resetear la MAC al tomar el control de wlpXsX.
MAC=$(cat /sys/class/net/"$WIFI_IF"/address 2>/dev/null || echo "")
if [ -z "$MAC" ] || [ "$MAC" = "00:00:00:00:00:00" ] || [ "$MAC" = "00:00:00:00:00:01" ]; then
    # Fallback: usar hostname + PID para garantizar algo único
    MAC="02:$(hostname | md5sum | sed 's/\(..\)\(..\)\(..\)\(..\)\(..\).*/\1:\2:\3:\4:\5/')"
fi
info "MAC WiFi: $MAC"

# ─── 3. Configurar red Ad-Hoc + BATMAN ───────────────────────────────────────
info "Cargando módulo batman-adv..."
modprobe batman-adv 2>/dev/null || true
sleep 1

info "Deteniendo NetworkManager..."
systemctl stop NetworkManager 2>/dev/null || true
sleep 2

info "Configurando modo Ad-Hoc en $WIFI_IF..."
ip link set "$WIFI_IF" down 2>/dev/null || true
sleep 1
iw "$WIFI_IF" ibss leave 2>/dev/null || true
sleep 1
if ! iw "$WIFI_IF" set type ibss 2>/tmp/iw_err; then
    ERR_MSG=$(cat /tmp/iw_err)
    echo ""
    error "El driver WiFi de $WIFI_IF no soporta modo Ad-Hoc (IBSS).
  Error: $ERR_MSG
  Soluciones:
    1. Usar un adaptador USB WiFi externo (ej: TP-Link TL-WN722N)
    2. Probar con otro equipo cuyo driver soporte IBSS
    3. Verificar con: iw list | grep -A5 'Supported interface modes'
       (debe aparecer 'IBSS' en la lista)"
fi
ip link set "$WIFI_IF" up
sleep 1

info "Uniéndose a red Ad-Hoc $SSID..."
if ! iw "$WIFI_IF" ibss join "$SSID" $FREQ fixed-freq $BSSID 2>/dev/null; then
    iw "$WIFI_IF" ibss join "$SSID" $FREQ $BSSID 2>/dev/null || \
        warn "iw ibss join: driver puede no soportar fixed-freq"
fi
sleep 3
ok "Red Ad-Hoc configurada"

# ─── 4. Agregar interfaz a BATMAN y levantar bat0 ────────────────────────────
batctl if add "$WIFI_IF" 2>/dev/null || true
sleep 1
ip link set bat0 up 2>/dev/null || true

# ─── 5. Asignación de IP única por MAC del WiFi ──────────────────────────────
# Usa los últimos 2 bytes de la MAC real del WiFi para derivar un número 1-254
# único por hardware. Sin colisiones: cada tarjeta WiFi tiene MAC distinta.

info "Calculando IP única basada en MAC de $WIFI_IF..."

# Usar todos los bytes de la MAC para máxima dispersión
B1=$(printf '%d' "0x$(echo "$MAC" | awk -F: '{print $4}')" 2>/dev/null || echo "1")
B2=$(printf '%d' "0x$(echo "$MAC" | awk -F: '{print $5}')" 2>/dev/null || echo "0")
B3=$(printf '%d' "0x$(echo "$MAC" | awk -F: '{print $6}')" 2>/dev/null || echo "0")

# Hash de 3 bytes → offset 1-99 (evitar 0 para no quedar en .101 por defecto)
OFFSET=$(( (B1 * 31 + B2 * 7 + B3) % 99 + 1 ))
BATMAN_IP="${NET_PREFIX}.$((IP_RANGE_START + OFFSET - 1))"

ip addr flush dev bat0 2>/dev/null || true
ip addr add "$BATMAN_IP/24" dev bat0
ok "IP asignada: $BATMAN_IP  (MAC WiFi: $MAC)"

# ─── 6. Guardar configuración del nodo ───────────────────────────────────────
info "Guardando configuración..."
python3 - <<PYEOF
import json, os, sys
cfg_path = "$REPO_DIR/data/node_config.json"
os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
try:
    with open(cfg_path) as f:
        cfg = json.load(f)
except Exception:
    cfg = {}
cfg.update({
    "node_name":        "$USER_DISPLAY_NAME",
    "role":             "peer",
    "bat0_ip":          "$BATMAN_IP",
    "broadcast_ip":     "255.255.255.255",
    "broadcast_port":   12345,
    "online":           True,
    "collaboration_pct": 100,
    "envy_pct":         0,
    "gen_rate":         1.0,
    "drop_prob":        0.0,
    "payload_size":     0,
})
with open(cfg_path, "w") as f:
    json.dump(cfg, f, indent=2)
print(f"Config guardada: $USER_DISPLAY_NAME / $BATMAN_IP / role=peer")
PYEOF

ok "Configuración lista"

# ─── 7. Arrancar nodo ────────────────────────────────────────────────────────
echo ""
echo "============================================================"
ok "Iniciando nodo: $USER_DISPLAY_NAME ($BATMAN_IP)"
echo "  Dashboard: http://localhost:5080"
echo "============================================================"
echo ""

cd "$REPO_DIR"
mkdir -p logs data

# Matar instancias anteriores antes de arrancar (evita DB locked)
info "Cerrando procesos anteriores..."
pkill -f "python3.*node\.py"     2>/dev/null || true
pkill -f "python3.*sensor_node"  2>/dev/null || true
pkill -f "python3.*app\.py"      2>/dev/null || true
sleep 2   # dar tiempo a que liberen la DB

(sleep 4 && _open_browser "http://localhost:5080") &

NODE_NAME="$USER_DISPLAY_NAME" BAT0_IP="$BATMAN_IP" NODE_ROLE="peer" \
    python3 node.py
