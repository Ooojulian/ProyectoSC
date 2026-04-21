#!/bin/bash
# Setup Red Ad-Hoc con NetworkManager
# Uso: sudo ./setup_adhoc.sh <ssid> <channel> <ip_address>

set -e

SSID="${1:-ProjectoSC}"
CHANNEL="${2:-6}"
IP_ADDRESS="${3:-192.168.100.1}"
SUBNET="192.168.100.0/24"

# Determinar la interfaz WiFi
WIFI_IF=$(iw dev | grep Interface | awk '{print $2}' | head -1)

if [ -z "$WIFI_IF" ]; then
    echo "❌ No se encontró interfaz WiFi"
    exit 1
fi

echo "🔧 Configurando red Ad-Hoc"
echo "  Interfaz: $WIFI_IF"
echo "  SSID: $SSID"
echo "  Canal: $CHANNEL"
echo "  IP: $IP_ADDRESS"

# Desactivar el gestor de red temporalmente
echo "⏸️  Deteniendo NetworkManager..."
sudo systemctl stop NetworkManager 2>/dev/null || true

# Poner la interfaz en modo monitor
echo "📡 Configurando interfaz en modo Ad-Hoc..."
sudo ip link set $WIFI_IF down
sudo iw $WIFI_IF set type ibss
sudo ip link set $WIFI_IF up

# Crear la red Ad-Hoc
echo "🌐 Creando red Ad-Hoc..."
sudo iw $WIFI_IF ibss join "$SSID" $CHANNEL

# Asignar IP
echo "🔗 Asignando dirección IP..."
sudo ip addr flush dev $WIFI_IF
sudo ip addr add $IP_ADDRESS/24 dev $WIFI_IF

echo "✅ Red Ad-Hoc configurada exitosamente"
echo ""
echo "Estado de la interfaz:"
ip addr show $WIFI_IF
echo ""
echo "Nodos de la red:"
iw $WIFI_IF station dump 2>/dev/null || echo "  Esperando otros nodos..."

# Crear archivo de configuración
cat > /home/julian/ProyectoSC/config/network_config.txt << EOF
WIFI_IF=$WIFI_IF
SSID=$SSID
CHANNEL=$CHANNEL
IP_ADDRESS=$IP_ADDRESS
SUBNET=$SUBNET
CREATED=$(date)
EOF

echo "📋 Configuración guardada en /home/julian/ProyectoSC/config/network_config.txt"
