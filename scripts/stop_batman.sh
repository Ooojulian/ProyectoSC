#!/bin/bash
# Detener BATMAN-adv y limpiar interfaces
# Uso: sudo ./stop_batman.sh [interface]

set -e

INTERFACE="${1:-wlan0}"
BATMAN_IF="bat0"

echo "🛑 Deteniendo BATMAN-adv..."

# Remover interfaz de batman
echo "🔌 Removiendo $INTERFACE de BATMAN..."
sudo ip link set $INTERFACE nomaster 2>/dev/null || true

# Eliminar interfaz batman
echo "🗑️  Eliminando interfaz $BATMAN_IF..."
sudo ip link delete $BATMAN_IF type batadv 2>/dev/null || true

# Descargar módulo batman
echo "📦 Descargando módulo batman-adv..."
sudo modprobe -r batman-adv 2>/dev/null || true

echo "✅ BATMAN-adv detenido"
echo ""
echo "Interfaces de red:"
ip link show | grep -E "^[0-9]+:"
