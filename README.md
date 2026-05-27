# ProyectoSC — Red Mesh Descentralizada con BATMAN-adv

Sistema de inventario distribuido sobre red mesh Ad-Hoc. Sin servidor central.
Los nodos se sincronizan entre sí por UDP broadcast sobre BATMAN-adv.

---

## Inicio rápido

```bash
git clone https://github.com/Ooojulian/ProyectoSC.git
cd ProyectoSC
sudo bash start.sh        # Ubuntu/Debian
# sudo bash startfedora.sh  # Fedora
```

Cuando pida tu nombre, ingrésalo. El script hace todo automáticamente:
- Instala `batman-adv`, `batctl`, `arping`, Flask
- Configura la red Ad-Hoc WiFi `ProyectoSC` (canal 6)
- Asigna una IP única al nodo (rango `192.168.200.101–200`)
- Arranca sensor + dashboard + panel de control
- Abre el dashboard en el navegador

**Todos los nodos son iguales** — no hay maestro ni configuración especial por rol.

---

## Acceder al sistema

| Servicio | URL |
|---|---|
| Dashboard principal | `http://localhost:5080` |
| Panel de control | `http://localhost:5001` |
| Desde otro nodo (IP bat0) | `http://192.168.200.XXX:5080` |

```bash
ip addr show bat0           # ver tu IP asignada
sudo batctl n               # ver vecinos en la malla
watch -n 2 'sudo batctl n'  # en vivo
```

---

## Detener todo

```bash
# Ctrl+C en la terminal donde corre start.sh
# O manualmente:
pkill -f node.py ; pkill -f sensor_node.py
pkill -f "app.py" ; pkill -f control_panel.py
sudo systemctl start NetworkManager
```

---

## Estructura del proyecto

```
ProyectoSC/
├── start.sh                ← Ubuntu/Debian: levanta red + arranca nodo
├── startfedora.sh          ← Fedora: equivalente a start.sh
│
├── node.py                 ← Launcher del nodo P2P (arrancado por start.sh)
├── sensor_node.py          ← Genera y recibe eventos UDP broadcast
├── provisioner.py          ← Servidor TCP (envía código/BD a nodos nuevos)
├── client_bootstrap.py     ← Auto-provisioning para nodos nuevos
├── control_panel.py        ← Panel de control Flask :5001
├── db.py                   ← Capa SQLite thread-safe
├── node_config.py          ← Config dinámica JSON
│
├── web_dashboard/
│   ├── app.py              ← Dashboard Flask :5080 + juego Blackjack P2P
│   └── templates/
│       ├── dashboard.html  ← Página principal (topología, chat, métricas)
│       ├── game.html       ← Juego Blackjack distribuido
│       └── control_panel.html ← UI del panel de control
│
├── data/
│   ├── inventory.db        ← Base de datos SQLite (ignorada en git)
│   └── node_config.json    ← Config actual del nodo
│
├── logs/                   ← Logs de ejecución (ignorados en git)
└── dev/test_local.py       ← Script de prueba local (no es parte del flujo P2P)
```

---

## Cómo funciona

### Flujo normal
1. Cada nodo genera eventos aleatorios (agregar/quitar ítems del inventario)
2. Los emite por **UDP broadcast** a toda la red (`puerto 12345`)
3. Todos los nodos los reciben y guardan en su BD local (SQLite)
4. **BATMAN-adv** enruta los paquetes por la mejor ruta disponible
5. Resultado: todos los nodos tienen el mismo inventario sin servidor central

### Auto-provisioning (nodo nuevo sin código)
Si un nodo nuevo no tiene el código aún, puede ejecutar `client_bootstrap.py`:
1. Escucha broadcast UDP para descubrir un nodo con provisioner activo
2. Conecta TCP al provisioner (`:12346`)
3. Recibe: ZIP con el código, dump de la BD actual, config JSON
4. Extrae, configura y arranca el nodo automáticamente

### Red BATMAN-adv
- Protocolo: **IBSS (Ad-Hoc WiFi)** + **BATMAN-adv** routing
- SSID: `ProyectoSC` | Canal: `6` (2.4 GHz)
- Subred: `192.168.200.0/24`
- Si un nodo cae, la red se re-enruta automáticamente

---

## Puertos

| Puerto | Protocolo | Uso |
|---|---|---|
| `12345` | UDP | Eventos del inventario (todos los nodos) |
| `12346` | TCP | Provisioning (nodos que corren provisioner.py) |
| `5080` | TCP | Dashboard web |
| `5001` | TCP | Panel de control |

---

## Variables de entorno (ajuste de comportamiento)

```bash
NODE_NAME="Node-1"   # Nombre del nodo
GEN_RATE=1.0         # Eventos por segundo
DROP_PROB=0.0        # Simular pérdida de paquetes (0.0–1.0)
PAYLOAD_SIZE=0       # Bytes extra por paquete (pruebas de carga)
BAT0_IP="..."        # IP manual en red BATMAN
```

---

## Solución de problemas

**No veo otros nodos en el dashboard**
```bash
iw <interfaz> info   # debe mostrar: ssid: ProyectoSC
# Los nodos aparecen en ~10 segundos
```

**"No se encontró interfaz WiFi"**
```bash
ip link show   # busca interfaz que empiece con w
# Editar start.sh línea 'candidates' si tu interfaz tiene nombre raro
```

**"Address already in use"**
```bash
pkill -f node.py ; pkill -f sensor_node.py
pkill -f "app.py" ; pkill -f control_panel.py
sudo bash start.sh
```

**batman-adv no carga (Ubuntu)**
```bash
sudo apt install -y linux-modules-extra-$(uname -r)
sudo modprobe batman-adv
```

**"ibss join: Device or resource busy"**
```bash
sudo systemctl stop NetworkManager
sudo bash start.sh
```

**"ModuleNotFoundError: No module named 'flask'"**
```bash
pip3 install flask --break-system-packages
```

**Logs en vivo**
```bash
tail -f logs/sensor.log
tail -f logs/dashboard.log
tail -f logs/node.log
```

---

## Métricas del dashboard

| Métrica | Descripción |
|---|---|
| `ρ (rho)` | Utilización del sistema (λ/μ), ideal < 0.8 |
| `L(q)` | Paquetes en cola |
| `W(q)` | Tiempo promedio en cola |
| `lat (ms)` | Latencia promedio de procesamiento |
| `PLR` | Packet Loss Rate |
| `sent/recv` | Eventos enviados/recibidos |
