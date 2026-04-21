#!/bin/bash
# Configurar red Ad-Hoc + BATMAN ahora mismo

set -e

SSID="ProyectoSC"
CHANNEL="6"
WIFI_IF="wlo1"
BATMAN_IP="192.168.200.101"

echo "🔧 Configurando red Ad-Hoc + BATMAN..."
echo "   Interfaz: $WIFI_IF"
echo "   SSID: $SSID"
echo "   Canal: $CHANNEL"
echo "   IP BATMAN: $BATMAN_IP"
echo ""

# 1. Desconectar del gestor de red
echo "1️⃣ Desconectando WiFi normal..."
nmcli device disconnect $WIFI_IF 2>/dev/null || true
sleep 2

# 2. Bajar interfaz wlo1
echo "2️⃣ Bajando interfaz WiFi..."
ip link set $WIFI_IF down

# 3. Poner en modo IBSS (Ad-Hoc)
echo "3️⃣ Configurando modo Ad-Hoc..."
iw $WIFI_IF set type ibss
ip link set $WIFI_IF up

# 4. Crear red Ad-Hoc
echo "4️⃣ Creando red Ad-Hoc ProyectoSC..."
iw $WIFI_IF ibss join "$SSID" $CHANNEL

sleep 2

# 5. Quitar IP anterior de bat0
echo "5️⃣ Configurando IP en BATMAN..."
ip addr flush dev bat0
ip addr add $BATMAN_IP/24 dev bat0

echo ""
echo "✅ Red Ad-Hoc + BATMAN configurados!"
echo ""
echo "Estado wlo1:"
ip addr show $WIFI_IF | grep -E "inet|state"
echo ""
echo "Estado bat0:"
ip addr show bat0 | grep -E "inet|state"
echo ""
echo "Nodos en la red Ad-Hoc:"
iw $WIFI_IF station dump 2>/dev/null || echo "Esperando otros nodos..."
echo ""
echo "Para iniciar el sensor ejecuta:"
echo "  NODE_NAME='Node-1' python3 sensor_node.py"
