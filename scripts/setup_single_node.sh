#!/bin/bash
# Setup completo de un nodo individual
# Uso: ./setup_single_node.sh <node_number> [interface]

set -e

NODE_NUM="${1:-1}"
INTERFACE="${2:-wlan0}"
NODE_NAME="Node-$NODE_NUM"
IP="192.168.200.$((100 + NODE_NUM))"

echo "🚀 Configurando nodo individual: $NODE_NAME"
echo "  IP: $IP"
echo "  Interfaz: $INTERFACE"

# Crear directorios si no existen
mkdir -p /home/julian/ProyectoSC/{data,logs,config}

# Exportar variables de entorno
export NODE_NAME=$NODE_NAME
export NODE_IP=$IP

echo "✅ Nodo listo para ejecutar el sensor"
echo ""
echo "Para iniciar el sensor, ejecuta:"
echo "  NODE_NAME='$NODE_NAME' python3 /home/julian/ProyectoSC/sensor_node.py"
echo ""
echo "Para iniciar el dashboard, en otra terminal:"
echo "  NODE_NAME='$NODE_NAME' python3 /home/julian/ProyectoSC/web_dashboard/app.py"
