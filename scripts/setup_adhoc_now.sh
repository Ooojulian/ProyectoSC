#!/bin/bash
# Configurar red Ad-Hoc + BATMAN ahora mismo
# Uso: sudo bash setup_adhoc_now.sh [IP] [NOMBRE_NODO]
#   IP por defecto: 192.168.200.101
#   Ejemplo nodo 2: sudo bash setup_adhoc_now.sh 192.168.200.102 Node-2

set -e

SSID="ProyectoSC"
CHANNEL="2437"   # canal 6 en MHz
WIFI_IF="wlo1"
BATMAN_IP="${1:-192.168.200.101}"
NODE_NAME="${2:-Node-1}"

echo "Configurando red Ad-Hoc + BATMAN..."
echo "   Interfaz:  $WIFI_IF"
echo "   SSID:      $SSID"
echo "   Canal:     $CHANNEL"
echo "   IP BATMAN: $BATMAN_IP"
echo "   Nodo:      $NODE_NAME"
echo ""

# 1. Instalar batctl si falta
if ! command -v batctl &>/dev/null; then
    echo "Instalando batctl..."
    apt-get install -y batctl 2>/dev/null || true
fi

# 2. Cargar modulo batman-adv
modprobe batman-adv 2>/dev/null || true

# 3. Detener NetworkManager para liberar la interfaz
echo "1. Deteniendo NetworkManager..."
systemctl stop NetworkManager
sleep 2

# 4. Bajar interfaz
echo "2. Bajando interfaz WiFi..."
ip link set $WIFI_IF down
sleep 1

# 5. Modo IBSS (Ad-Hoc)
echo "3. Configurando modo Ad-Hoc..."
iw $WIFI_IF set type ibss
ip link set $WIFI_IF up

# 6. Unirse a red Ad-Hoc
echo "4. Creando red Ad-Hoc $SSID..."
iw $WIFI_IF ibss join "$SSID" $CHANNEL
sleep 2

# 7. Agregar wlo1 a batman si no está ya
if command -v batctl &>/dev/null; then
    batctl if add $WIFI_IF 2>/dev/null || true
fi

# 8. Configurar IP en bat0
echo "5. Configurando IP $BATMAN_IP en bat0..."
ip link set bat0 up 2>/dev/null || true
ip addr flush dev bat0 2>/dev/null || true
ip addr add $BATMAN_IP/24 dev bat0

# 9. Guardar config en node_config.json
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$SCRIPT_DIR/data/node_config.json"
if [ -f "$CONFIG" ]; then
    python3 -c "
import json, sys
with open('$CONFIG') as f: c = json.load(f)
c['bat0_ip'] = '$BATMAN_IP'
c['node_name'] = '$NODE_NAME'
with open('$CONFIG','w') as f: json.dump(c, f, indent=2)
print('Config actualizada: bat0_ip=$BATMAN_IP node_name=$NODE_NAME')
"
fi

echo ""
echo "Red Ad-Hoc + BATMAN configurados!"
echo ""
echo "Estado bat0:"
ip addr show bat0 | grep -E "inet|state"
echo ""
echo "Vecinos WiFi:"
iw $WIFI_IF station dump 2>/dev/null || echo "(esperando otros nodos...)"
echo ""
if command -v batctl &>/dev/null; then
    echo "Vecinos BATMAN:"
    batctl n 2>/dev/null || echo "(esperando...)"
fi
echo ""
echo "Para iniciar: NODE_NAME='$NODE_NAME' python3 $SCRIPT_DIR/master_node.py"
