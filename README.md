# Proyecto Sistemas Complejos - Red Mesh Descentralizada

Sistema distribuido de red Ad-Hoc con protocolo BATMAN-adv para simular y analizar propiedades de sistemas complejos.

## Estructura del Proyecto

```
ProyectoSC/
├── sensor_node.py           # Script principal del nodo sensor
├── web_dashboard/
│   ├── app.py              # Aplicación Flask para dashboard
│   └── templates/
│       └── dashboard.html   # Interfaz web
├── scripts/
│   ├── setup_adhoc.sh      # Configurar red Ad-Hoc
│   ├── setup_single_node.sh # Configurar nodo individual
│   └── stop_batman.sh      # Detener BATMAN
├── config/
│   └── default.env         # Variables de configuración
├── data/
│   └── inventory.csv       # Base de datos local de cada nodo
└── logs/
    └── sensor.log          # Logs de ejecución
```

## Requisitos Previos

### Sistemas Operativos Requeridos
- Ubuntu Linux 22.04 LTS o superior
- Todos los nodos con Linux (flexible como se especifica)

### Dependencias del Sistema
```bash
# Instalar herramientas de red
sudo apt update
sudo apt install -y iw wpasupplicant network-manager batctl

# Instalar BATMAN-adv kernel module
sudo apt install -y batman-adv

# Instalar Python y librerías
sudo apt install -y python3.11 python3-pip
pip3 install flask
```

### Hardware Requerido
- 4 Computadoras/laptops con tarjeta WiFi que soporte modo Ad-Hoc
- Tarjetas WiFi deben soportar modo monitor/Ad-Hoc (verificar con: `iw list`)
- 1 Celular (opcional, para cliente adicional)

## Instalación

### Paso 1: Preparar el Sistema
```bash
# Hacer scripts ejecutables
chmod +x /home/julian/ProyectoSC/scripts/*.sh

# Crear directorios necesarios
mkdir -p /home/julian/ProyectoSC/{data,logs,config}
```

### Paso 2: Configurar Variables de Entorno
```bash
# Editar el archivo de configuración
nano /home/julian/ProyectoSC/config/default.env
```

## Ejecución

### Modo 1: Nodo Individual (Sin Red Mesh Aún)

**Terminal 1 - Ejecutar el sensor:**
```bash
export NODE_NAME="Node-1"
python3 /home/julian/ProyectoSC/sensor_node.py
```

**Terminal 2 - Ejecutar el dashboard:**
```bash
export NODE_NAME="Node-1"
python3 /home/julian/ProyectoSC/web_dashboard/app.py
```

**Acceso:**
- Dashboard: http://localhost:5000
- Logs: /home/julian/ProyectoSC/logs/sensor.log
- Datos: /home/julian/ProyectoSC/data/inventory.csv

### Modo 2: Red Ad-Hoc (Cuando Tengas Todos los Nodos)

**En TODOS los computadores:**

1. Configurar la red Ad-Hoc (requiere permisos sudo):
```bash
sudo /home/julian/ProyectoSC/scripts/setup_adhoc.sh ProyectoSC 6
```

2. Instalar y cargar BATMAN-adv:
```bash
sudo modprobe batman-adv
sudo ip link add name bat0 type batadv
```

3. Agregar interfaz WiFi a BATMAN:
```bash
sudo ip link set wlan0 master bat0
sudo ip addr add 192.168.200.10X/24 dev bat0  # X = número de nodo (1,2,3,4)
```

4. Ejecutar el sensor (en cada computador):
```bash
export NODE_NAME="Node-1"  # Cambiar número de nodo
python3 /home/julian/ProyectoSC/sensor_node.py &

# Dashboard en otra terminal
export NODE_NAME="Node-1"
python3 /home/julian/ProyectoSC/web_dashboard/app.py
```

## Configuración Ajustable

Modificar estos parámetros para probar propiedades del sistema complejo:

```bash
# Tasa de generación de eventos (eventos/segundo)
export GEN_RATE=1.0    # Ligero
export GEN_RATE=10.0   # Moderado
export GEN_RATE=50.0   # Pesado (estrés)

# Simular pérdida de paquetes (interferencia)
export DROP_PROB=0.1   # 10% de pérdida
export DROP_PROB=0.3   # 30% de pérdida

# Aumentar tamaño de datos
export PAYLOAD_SIZE=1000  # Agregar 1KB de carga

# Tamaño del catálogo
export CATALOG_SIZE=5      # Pocos items
export CATALOG_SIZE=100    # Muchos items
```

## Pruebas del Sistema

### Prueba 1: Consistencia Distribuida
1. Ejecutar 4 nodos simultáneamente
2. Dejar que generen eventos durante 5 minutos
3. Verificar que todos los CSV tengan los mismos registros
4. Comando para verificar:
```bash
wc -l /home/julian/ProyectoSC/data/inventory.csv  # En cada nodo
```

### Prueba 2: Tolerancia a Fallos
1. Ejecutar los 4 nodos
2. Apagar uno de los nodos intermedios (Ctrl+C)
3. Verificar que los otros 3 sigan recibiendo datos
4. Verificar latencias en el dashboard

### Prueba 3: Rendimiento (Teoría de Colas M/M/1)
1. Aumentar GEN_RATE a 50 eventos/segundo
2. Monitorear métricas en el dashboard:
   - ρ (utilización del sistema)
   - W_q (tiempo en cola)
   - Latencia promedio
3. Verificar que ρ < 1 para evitar saturación

### Prueba 4: Interferencia
1. Configurar DROP_PROB=0.2 (20% de pérdida)
2. Ejecutar nodos
3. Observar cómo se recupera el sistema
4. Comparar métricas con y sin interferencia

## Métricas de Rendimiento

El sistema registra automáticamente:

- **Latencia de Sincronización (τ)**: Tiempo desde creación hasta almacenamiento
- **Tasa de Pérdida**: Paquetes perdidos / total enviados
- **Throughput**: Bytes procesados por segundo
- **ρ (Factor de Utilización)**: λ/μ en modelo M/M/1
- **W_q (Tiempo en Cola)**: Tiempo esperado antes de procesar

Ver en: Dashboard → Métricas

## Resolución de Problemas

### "No se encuentra interfaz WiFi"
```bash
# Ver interfaces disponibles
iw dev
ip link show

# Buscar tarjeta WiFi
lspci | grep -i network
```

### "Error: Permiso denegado"
```bash
# Los scripts de red requieren sudo
sudo -l  # Ver permisos sudoers
sudo ./scripts/setup_adhoc.sh
```

### "Puerto 5000 ya está en uso"
```bash
# Ver procesos
sudo lsof -i :5000
# O usar puerto diferente:
export DASHBOARD_PORT=5001
```

### "CSV corrupto o vacío"
```bash
# Recrear CSV:
rm /home/julian/ProyectoSC/data/inventory.csv
# El script lo recreará automáticamente al iniciar
```

## Documentación de Capas

### Capa 1: Física
- Red Ad-Hoc sin router central
- Cada nodo se conecta directamente con otros
- Configurada con NetworkManager

### Capa 2: Enrutamiento
- Protocolo BATMAN-adv
- Auto-organización de rutas
- Tolerancia a fallas de nodos intermedios
- Interfaz virtual: bat0

### Capa 3: Aplicación
- Script Python multihilo
- Generador de eventos aleatorios
- Recepción UDP broadcast concurrente
- Persistencia en CSV
- Dashboard Flask para visualización

## Contacto y Soporte

**Proyecto**: Sistema de Sistemas Complejos - Universidad Sergio Arboleda

**Integrantes**:
- Cristian Andres Reinales Herrera
- Julian David Cristancho Bustos
- Julian David Beltran Rodrigez
- Daniel Ricardo Reyes Aroca

**Última actualización**: 2026-04-19
