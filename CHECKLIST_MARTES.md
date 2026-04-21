# ✅ Checklist Martes - Día de la Integración con 4 Computadores

## 📋 ANTES DEL MARTES (Hoy-Mañana)

- [x] Código completado y testeado
- [x] Dashboard funcionando localmente
- [x] test_local.py validando lógica
- [ ] **IMPORTANTE:** Instalar Flask: `pip3 install flask`
- [ ] Ejecutar test_local.py una vez para confirmar que todo funciona
- [ ] Revisar QUICKSTART.md y README.md
- [ ] Descargar proyecto en todos los 4 computadores (copiar la carpeta ProyectoSC)

## 📅 EL MARTES - DÍA D

### ⏰ PREPARACIÓN (30 minutos)

#### EN CADA UNO DE LOS 4 COMPUTADORES:

```bash
# 1. Copiar carpeta ProyectoSC (si no la tienen)
cp -r /home/julian/ProyectoSC ~/ProyectoSC

# 2. Crear directorios necesarios
mkdir -p ~/ProyectoSC/{data,logs}

# 3. Verificar permisos de scripts
chmod +x ~/ProyectoSC/scripts/*.sh

# 4. Instalar Flask (si no lo tienen)
pip3 install flask
```

### 🔧 CONFIGURAR RED AD-HOC (15 minutos por computador)

**EN CADA COMPUTADOR:**

```bash
# Paso 1: Crear red Ad-Hoc
# (Reemplazar "6" por el canal - 1, 6, 11, etc., dependiendo de interferencia)
sudo ~/ProyectoSC/scripts/setup_adhoc.sh ProyectoSC 6

# Verificar que la interfaz se creó:
ip addr show wlan0

# Debería mostrar algo como: inet 192.168.100.X/24
```

**VALIDACIÓN:** Ping entre nodos
```bash
# Desde Node-1, hacer ping a Node-2 (si está en 192.168.100.2):
ping 192.168.100.2

# Debería recibir respuestas ✓
```

### ⚙️ INSTALAR Y CARGAR BATMAN-ADV (10 minutos por computador)

**EN CADA COMPUTADOR:**

```bash
# Paso 1: Instalar herramientas (si no están)
! sudo apt install -y batctl iw wpasupplicant

# Paso 2: Cargar módulo batman
sudo modprobe batman-adv

# Paso 3: Crear interfaz virtual bat0
sudo ip link add name bat0 type batadv

# Paso 4: Agregar interfaz WiFi a BATMAN
sudo ip link set wlan0 master bat0

# Paso 5: Asignar IP estática
# ⚠️ IMPORTANTE: Cambiar X según el nodo (1, 2, 3, 4)
# Node-1: 192.168.200.101
# Node-2: 192.168.200.102
# Node-3: 192.168.200.103
# Node-4: 192.168.200.104

sudo ip addr add 192.168.200.10X/24 dev bat0

# Paso 6: Activar interfaz
sudo ip link set bat0 up
```

**VALIDACIÓN:** Topología BATMAN
```bash
# Ver topología de la malla:
batctl topology

# Debería mostrar los otros nodos conectados ✓
```

### 🚀 EJECUTAR SENSOR EN CADA COMPUTADOR (5 minutos)

**TERMINAL 1 - Ejecutar el sensor (backend):**
```bash
# Node-1
NODE_NAME="Node-1" python3 ~/ProyectoSC/sensor_node.py

# Node-2
NODE_NAME="Node-2" python3 ~/ProyectoSC/sensor_node.py

# Node-3
NODE_NAME="Node-3" python3 ~/ProyectoSC/sensor_node.py

# Node-4
NODE_NAME="Node-4" python3 ~/ProyectoSC/sensor_node.py
```

**TERMINAL 2 - Ejecutar dashboard (interfaz web):**
```bash
# Node-1
NODE_NAME="Node-1" python3 ~/ProyectoSC/web_dashboard/app.py

# Node-2
NODE_NAME="Node-2" python3 ~/ProyectoSC/web_dashboard/app.py

# Node-3
NODE_NAME="Node-3" python3 ~/ProyectoSC/web_dashboard/app.py

# Node-4
NODE_NAME="Node-4" python3 ~/ProyectoSC/web_dashboard/app.py
```

### 📊 VERIFICAR CONECTIVIDAD (5 minutos)

**DESDE CUALQUIER NAVEGADOR:**

```
Node-1: http://192.168.200.101:5000
Node-2: http://192.168.200.102:5000
Node-3: http://192.168.200.103:5000
Node-4: http://192.168.200.104:5000
```

**¿QUE BUSCAR?**
- [ ] Dashboard cargando datos
- [ ] "Total Recibidos" > 0
- [ ] Latencia promedio visible
- [ ] Distribución de nodos mostrada
- [ ] Tabla de inventario con registros

---

## 🧪 PRUEBAS A REALIZAR

### PRUEBA 1: Consistencia Distribuida (15 minutos)

**Objetivo:** Verificar que todos los nodos reciben los mismos eventos.

```bash
# 1. Dejar que el sistema funcione 5 minutos sin interrupciones
# 2. En cada computador, abrir terminal y ejecutar:

# Contar filas en CSV
wc -l ~/ProyectoSC/data/inventory.csv

# RESULTADO ESPERADO:
# Node-1: 120 líneas
# Node-2: 120 líneas
# Node-3: 120 líneas
# Node-4: 120 líneas
# (El número exacto puede variar, pero deben ser IGUALES o muy parecidos)
```

**✅ ÉXITO SI:** Todos los números son similares (diferencia < 10%)

---

### PRUEBA 2: Tolerancia a Fallos (10 minutos)

**Objetivo:** Verificar que el sistema continúa funcionando si se apaga un nodo.

```bash
# 1. Dejar que funcione 2 minutos normalmente
# 2. En Node-2, presionar Ctrl+C para apagarlo
# 3. Esperar 2 minutos más
# 4. Verificar en Node-1, Node-3 y Node-4:

# Revisar logs para confirmar que sigue recibiendo:
tail -50 ~/ProyectoSC/logs/sensor.log

# DEBE MOSTRAR: "Evento recibido de Node-1", "Node-3", "Node-4"
# sin "Node-2" después que se apagó
```

**✅ ÉXITO SI:** Los otros 3 nodos siguen recibiendo datos entre sí.

---

### PRUEBA 3: Rendimiento bajo Carga (15 minutos)

**Objetivo:** Medir cómo se comporta el sistema bajo estrés.

```bash
# 1. Apagar el sensor en todos los nodos (Ctrl+C)
# 2. Reiniciar CON CARGA ALTA:

GEN_RATE=50 NODE_NAME="Node-1" python3 ~/ProyectoSC/sensor_node.py
GEN_RATE=50 NODE_NAME="Node-2" python3 ~/ProyectoSC/sensor_node.py
GEN_RATE=50 NODE_NAME="Node-3" python3 ~/ProyectoSC/sensor_node.py
GEN_RATE=50 NODE_NAME="Node-4" python3 ~/ProyectoSC/sensor_node.py

# 3. Monitorear en el dashboard:
# - Ver ρ (utilización) - debe estar entre 0.5 y 0.95
# - Ver W(q) (tiempo en cola)
# - Verificar latencia promedio

# Después de 3 minutos, ir a Node-1 y ver:
tail ~/ProyectoSC/logs/sensor.log
```

**✅ ÉXITO SI:** El sistema procesa datos sin saturarse (ρ < 0.99)

---

### PRUEBA 4: Interferencia y Recuperación (15 minutos)

**Objetivo:** Simular pérdida de paquetes y verificar recuperación.

```bash
# 1. Apagar sensores actuales
# 2. Reiniciar CON INTERFERENCIA:

DROP_PROB=0.2 NODE_NAME="Node-1" python3 ~/ProyectoSC/sensor_node.py
DROP_PROB=0.2 NODE_NAME="Node-2" python3 ~/ProyectoSC/sensor_node.py
DROP_PROB=0.2 NODE_NAME="Node-3" python3 ~/ProyectoSC/sensor_node.py
DROP_PROB=0.2 NODE_NAME="Node-4" python3 ~/ProyectoSC/sensor_node.py

# 3. Ejecutar durante 3 minutos
# 4. Comparar métricas:
# - PLR (Packet Loss Rate) debe ser ~0.2 (20%)
# - Sistema debe recuperarse y sincronizar igual

# Después de 3 minutos:
wc -l ~/ProyectoSC/data/inventory.csv
```

**✅ ÉXITO SI:** Sistema tolera 20% de pérdida y sigue sincronizando.

---

## 📊 MÉTRICAS A REGISTRAR

Para el informe/presentación, registrar:

| Métrica | Prueba 1 | Prueba 2 | Prueba 3 | Prueba 4 |
|---------|----------|----------|----------|----------|
| Latencia (ms) | ___ | ___ | ___ | ___ |
| Throughput | ___ | ___ | ___ | ___ |
| ρ (utilización) | ___ | ___ | ___ | ___ |
| Registros Node-1 | ___ | ___ | ___ | ___ |
| Registros Node-2 | ___ | ___ | ___ | ___ |
| Registros Node-3 | ___ | ___ | ___ | ___ |
| Registros Node-4 | ___ | ___ | ___ | ___ |

---

## 🛠️ TROUBLESHOOTING RÁPIDO

| Problema | Solución |
|----------|----------|
| "Interface not found" | Verificar: `iw dev` y `ip link show` |
| "Port already in use" | Cambiar puerto: `DASHBOARD_PORT=5001` |
| "Permission denied" | Usar `sudo` o `chmod +x` |
| "No data in CSV" | Revisar logs: `tail -100 logs/sensor.log` |
| "No connection between nodes" | Verificar IPs con `ip addr show` |
| "BATMAN no conecta" | Esperar 30s para que converja, revisar batctl |
| "CSV vacío o muy pequeño" | Proceso recién iniciado, esperar 30-60s |

---

## 📝 NOTAS IMPORTANTES

1. **Las IPs deben ser diferentes en cada nodo** (X = 1, 2, 3, 4)
2. **El dashboard toma 10 segundos en actualizar** - ser paciente
3. **Los CSVs se sincronizan automáticamente** - ver con `wc -l`
4. **Ctrl+C detiene ambos procesos** (sensor y dashboard juntos si están en mismo terminal)
5. **Ejecutar sensor PRIMERO, dashboard DESPUÉS**

---

## 🎯 ORDEN RECOMENDADO PARA EL DÍA

```
08:00 - Instalación del proyecto en 4 computadores (30 min)
08:30 - Configurar red Ad-Hoc en cada máquina (60 min)
09:30 - Instalar BATMAN-adv en cada máquina (40 min)
10:10 - Ejecutar sensores en todos (5 min)
10:15 - Ejecutar dashboards en todos (5 min)
10:20 - PAUSA 5 minutos para que se estabilice
10:25 - Prueba 1: Consistencia (15 min)
10:40 - Prueba 2: Tolerancia a fallos (10 min)
10:50 - Prueba 3: Rendimiento (15 min)
11:05 - Prueba 4: Interferencia (15 min)
11:20 - Documentar resultados y tomar screenshots
```

---

## 📸 CAPTURAS A TOMAR PARA LA PRESENTACIÓN

- [ ] Dashboard de cada nodo funcionando
- [ ] Logs mostrando "Evento recibido"
- [ ] CSV con datos sincronizados
- [ ] Prueba de apagado de nodo (otros siguen funcionando)
- [ ] Gráficos de latencia y throughput
- [ ] Terminal mostrando topology de BATMAN

---

## ✅ CHECKLIST FINAL

- [ ] Los 4 computadores con código instalado
- [ ] Flask instalado en cada máquina
- [ ] Red Ad-Hoc funcionando (ping entre nodos)
- [ ] BATMAN-adv cargado y convergido
- [ ] Sensores ejecutándose sin errores
- [ ] Dashboards accesibles desde navegador
- [ ] CSVs sincronizados (misma cantidad de líneas)
- [ ] Todos los tests pasados

---

**¡ÉXITO EL MARTES! 🎉**

Cualquier duda antes de ese día, revisar README.md o QUICKSTART.md
