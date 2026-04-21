# ProyectoSC - Red Mesh Descentralizada con BATMAN-adv

Sistema de inventario distribuido sobre red mesh Ad-Hoc. Sin servidor central.
Los nodos se sincronizan entre sí por UDP broadcast sobre BATMAN-adv.

## Lee esto primero

| Archivo | Para quién |
|---|---|
| `1_JULIAN_INSTRUCCIONES.txt` | Julian (nodo maestro) |
| `2_COMPANERO_INSTRUCCIONES.txt` | Compañeros (nodos nuevos) |
| `3_COMO_FUNCIONA.txt` | Referencia técnica del sistema |

## Resumen del flujo

1. Julian ejecuta `setup_adhoc_now.sh` → levanta la red mesh
2. Julian ejecuta `master_node.py` → arranca todos los servicios
3. Compañeros instalan `batctl` y ejecutan `client_bootstrap.py`
4. El sistema provisiona a los compañeros automáticamente (código + BD + config)
5. Todos los nodos intercambian eventos por UDP, BATMAN enruta

## Estructura

```
ProyectoSC/
├── master_node.py          ← Arranca todo en el nodo de Julian
├── client_bootstrap.py     ← Los compañeros ejecutan esto
├── sensor_node.py          ← Genera y recibe eventos UDP
├── provisioner.py          ← Envía código/BD a nodos nuevos
├── web_dashboard/app.py    ← Dashboard Flask :5000
├── control_panel.py        ← Panel de control :5001
├── db.py                   ← Capa SQLite
├── node_config.py          ← Config dinámica JSON
└── scripts/
    ├── setup_adhoc_now.sh  ← Levanta red Ad-Hoc (Julian)
    └── stop_batman.sh      ← Apaga la red mesh
```
