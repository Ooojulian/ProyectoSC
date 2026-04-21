# 🚀 Guía de Inicio Rápido - ProyectoSC

## ⚡ Inicio en 5 minutos

### 1️⃣ Instalar dependencias (una sola vez)

```bash
# Instalar Python packages
pip3 install flask

# Herramientas de red (requiere sudo)
! sudo apt install -y batctl iw wpasupplicant
```

### 2️⃣ Prueba local INMEDIATA (sin red mesh)

```bash
# Terminal 1 - Ejecutar sensor local (4 nodos simulados)
python3 /home/julian/ProyectoSC/test_local.py --nodes 4 --duration 120

# O más simple:
python3 /home/julian/ProyectoSC/test_local.py
```

**Qué sucede:**
- ✅ Crea 4 nodos simulados en tu máquina
- ✅ Genera eventos automáticamente
- ✅ Intercambia datos simulando red mesh
- ✅ Después de 60s, muestra estadísticas

### 3️⃣ Prueba con Dashboard

**Terminal 1:**
```bash
export NODE_NAME="Node-1"
python3 /home/julian/ProyectoSC/sensor_node.py
```

**Terminal 2:**
```bash
export NODE_NAME="Node-1"
python3 /home/julian/ProyectoSC/web_dashboard/app.py
```

**Luego abre:** http://localhost:5000

## 🎯 Casos de Uso

### Caso 1: Testing sin Red Mesh Física
```bash
# Simular 4 nodos en tu máquina durante 5 minutos
python3 /home/julian/ProyectoSC/test_local.py --nodes 4 --duration 300
```

### Caso 2: Testing con Carga Alta
```bash
# Generar eventos rápidamente
GEN_RATE=50 python3 /home/julian/ProyectoSC/sensor_node.py
```

### Caso 3: Simular Interferencia
```bash
# 10% de paquetes se pierden
DROP_PROB=0.1 python3 /home/julian/ProyectoSC/sensor_node.py
```

### Caso 4: Monitorear Métricas en Vivo
```bash
# Terminal 1: Sensor
NODE_NAME="Node-1" python3 sensor_node.py &

# Terminal 2: Dashboard
NODE_NAME="Node-1" python3 web_dashboard/app.py

# Terminal 3: Ver logs en tiempo real
tail -f /home/julian/ProyectoSC/logs/sensor.log
```

## 📊 Variables de Configuración

Cambiar antes de ejecutar:

```bash
# Tasa de generación (eventos/segundo)
export GEN_RATE=0.5      # Muy lento
export GEN_RATE=10       # Normal
export GEN_RATE=100      # Estrés

# Simular pérdida de paquetes
export DROP_PROB=0.1     # 10% loss
export DROP_PROB=0.5     # 50% loss

# Aumentar tamaño de datos
export PAYLOAD_SIZE=5000  # 5KB por paquete

# Nombre del nodo
export NODE_NAME="Node-2"
```

## 🔍 Monitorear Resultados

### Ver CSV actualizado en vivo:
```bash
watch -n 1 'tail -5 /home/julian/ProyectoSC/data/inventory.csv'
```

### Ver logs:
```bash
tail -f /home/julian/ProyectoSC/logs/sensor.log
```

### Contar registros:
```bash
wc -l /home/julian/ProyectoSC/data/inventory.csv
```

## 🔗 Para la Red Mesh Real (El Martes)

Cuando tus compañeros traigan sus computadores:

1. **En CADA computador**, ejecutar:
```bash
! sudo /home/julian/ProyectoSC/scripts/setup_adhoc.sh ProyectoSC 6
```

2. **En CADA computador**, cargar BATMAN:
```bash
! sudo modprobe batman-adv
! sudo ip link add name bat0 type batadv
! sudo ip link set wlan0 master bat0
! sudo ip addr add 192.168.200.10X/24 dev bat0
```
(Reemplazar X con: 1, 2, 3, 4 para cada nodo)

3. **En CADA computador**:
```bash
NODE_NAME="Node-X" python3 /home/julian/ProyectoSC/sensor_node.py &
NODE_NAME="Node-X" python3 /home/julian/ProyectoSC/web_dashboard/app.py &
```

4. **Desde cualquier navegador en cualquier computador:**
- Node 1: http://192.168.200.101:5000
- Node 2: http://192.168.200.102:5000
- Node 3: http://192.168.200.103:5000
- Node 4: http://192.168.200.104:5000

## ✅ Checklist de Preparación

- [ ] Python 3 instalado: `python3 --version`
- [ ] Flask instalado: `pip3 install flask`
- [ ] Proyecto clonado: `/home/julian/ProyectoSC/`
- [ ] Test local funcionando: `python3 test_local.py`
- [ ] Dashboard accesible: http://localhost:5000
- [ ] Archivos CSV se generan: `ls /home/julian/ProyectoSC/data/`

## 🆘 Problemas Comunes

**"ModuleNotFoundError: No module named 'flask'"**
```bash
pip3 install flask
```

**"Permission denied" en setup_adhoc.sh**
```bash
chmod +x /home/julian/ProyectoSC/scripts/*.sh
```

**"Port 5000 already in use"**
```bash
# Cambiar a otro puerto
DASHBOARD_PORT=5001 python3 web_dashboard/app.py
```

**No aparecen datos en CSV**
- Verificar que el script está corriendo: `ps aux | grep sensor_node`
- Ver logs: `tail /home/julian/ProyectoSC/logs/sensor.log`

## 📞 Próximos Pasos

1. ✅ **Hoy (antes del martes):** Ejecutar `test_local.py` y verificar que todo funciona
2. ✅ **Mañana:** Probar configuraciones con diferentes GEN_RATE y DROP_PROB
3. 🔜 **El martes:** Conectar 4 computadores en red mesh real
4. 🔜 **Presentación:** Mostrar cómo el sistema se auto-organiza sin nodo central

---

**¡Éxito! Cualquier duda, revisa el README.md completo.**
