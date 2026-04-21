#!/usr/bin/env python3
"""
Script de prueba local - Simula múltiples nodos en una sola máquina
Útil para testing antes de la implementación en red mesh real
"""

import subprocess
import time
import os
import signal
import sys
from pathlib import Path

class LocalTest:
    def __init__(self, num_nodes=4):
        self.num_nodes = num_nodes
        self.processes = []
        self.base_dir = Path("/home/julian/ProyectoSC")

    def setup(self):
        """Preparar directorios y archivos"""
        print("🔧 Preparando ambiente de prueba...")

        # Crear directorios
        (self.base_dir / "data").mkdir(exist_ok=True)
        (self.base_dir / "logs").mkdir(exist_ok=True)

        # Crear CSVs separados para cada nodo
        for i in range(1, self.num_nodes + 1):
            csv_file = self.base_dir / "data" / f"inventory_node{i}.csv"
            with open(csv_file, 'w') as f:
                f.write("message_id,origin_node,origin_id,timestamp_created,timestamp_received,action,item,latency_ms\n")

        print(f"✅ Ambiente preparado para {self.num_nodes} nodos")

    def start_node(self, node_num):
        """Inicia un nodo simulado"""
        env = os.environ.copy()
        env['NODE_NAME'] = f"Node-{node_num}"
        env['GEN_RATE'] = "1.0"
        env['CATALOG_SIZE'] = "10"
        env['DROP_PROB'] = "0.0"

        print(f"🚀 Iniciando {env['NODE_NAME']}...")

        # Crear log file único
        log_file = self.base_dir / "logs" / f"sensor_node{node_num}.log"

        with open(log_file, 'w') as log:
            process = subprocess.Popen(
                ["python3", str(self.base_dir / "sensor_node.py")],
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid  # Crear nuevo grupo de procesos
            )
            self.processes.append((process, node_num, os.getpgid(process.pid)))

    def start_dashboard(self, node_num):
        """Inicia el dashboard para un nodo"""
        env = os.environ.copy()
        env['NODE_NAME'] = f"Node-{node_num}"
        env['FLASK_ENV'] = "development"

        port = 5000 + node_num

        print(f"📊 Dashboard Node-{node_num} en http://localhost:{port}")

        with open(self.base_dir / "logs" / f"dashboard_node{node_num}.log", 'w') as log:
            process = subprocess.Popen(
                ["python3", "-m", "flask", "run", "--port", str(port), "--host", "0.0.0.0"],
                env=env,
                cwd=str(self.base_dir / "web_dashboard"),
                stdout=log,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid
            )
            self.processes.append((process, f"Dashboard-{node_num}", os.getpgid(process.pid)))

    def run_test(self, duration=60, with_dashboards=False):
        """Ejecutar prueba local"""
        print(f"\n📡 Iniciando prueba de {self.num_nodes} nodos por {duration} segundos\n")

        # Iniciar nodos
        for i in range(1, self.num_nodes + 1):
            self.start_node(i)
            if with_dashboards:
                time.sleep(1)  # Pequeña pausa

        time.sleep(2)

        # Iniciar dashboards (opcional)
        if with_dashboards:
            for i in range(1, self.num_nodes + 1):
                self.start_dashboard(i)
                time.sleep(1)

        try:
            # Ejecutar por X segundos
            for remaining in range(duration, 0, -10):
                print(f"\n⏱️  Ejecutándose... {remaining}s restantes")
                print(f"   Procesos activos: {len([p for p in self.processes if p[0].poll() is None])}")

                time.sleep(10)

        except KeyboardInterrupt:
            print("\n\n⏸️  Deteniendo prueba...")

        finally:
            self.cleanup()
            self.show_results()

    def cleanup(self):
        """Detener todos los procesos"""
        print("\n🛑 Deteniendo procesos...")

        for process, name, pgid in self.processes:
            try:
                if process.poll() is None:  # Si aún está vivo
                    os.killpg(pgid, signal.SIGTERM)
                    print(f"   ✓ {name} detenido")
            except Exception as e:
                print(f"   ✗ Error deteniendo {name}: {e}")

        time.sleep(1)

        # Forzar kill si es necesario
        for process, name, pgid in self.processes:
            try:
                if process.poll() is None:
                    os.killpg(pgid, signal.SIGKILL)
            except:
                pass

    def show_results(self):
        """Mostrar resultados de la prueba"""
        print("\n" + "="*60)
        print("📊 RESULTADOS DE LA PRUEBA")
        print("="*60 + "\n")

        # Contar registros en cada CSV
        totals = {}
        for i in range(1, self.num_nodes + 1):
            csv_file = self.base_dir / "data" / f"inventory_node{i}.csv"
            try:
                with open(csv_file) as f:
                    count = len(f.readlines()) - 1  # Restar header
                    totals[f"Node-{i}"] = count
            except:
                totals[f"Node-{i}"] = 0

        print("📦 Total de registros por nodo:")
        for node, count in totals.items():
            print(f"   {node}: {count} registros")

        # Mostrar estadísticas agregadas
        total_all = sum(totals.values())
        avg_per_node = total_all / self.num_nodes if self.num_nodes > 0 else 0

        print(f"\n📈 Estadísticas:")
        print(f"   Total de registros: {total_all}")
        print(f"   Promedio por nodo: {avg_per_node:.1f}")
        print(f"   Varianza: {'✓ Bajo' if abs(max(totals.values()) - min(totals.values())) < avg_per_node * 0.2 else '✗ Alto'}")

        # Mostrar logs
        print(f"\n📝 Logs disponibles en:")
        for i in range(1, self.num_nodes + 1):
            log_file = self.base_dir / "logs" / f"sensor_node{i}.log"
            print(f"   {log_file}")

        print(f"\n✅ Prueba completada. Revisa los logs para más detalles.")
        print(f"\n💾 Datos persistidos en: {self.base_dir / 'data'}")

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test local del sistema de nodos mesh")
    parser.add_argument("--nodes", type=int, default=4, help="Número de nodos a simular")
    parser.add_argument("--duration", type=int, default=60, help="Duración de la prueba en segundos")
    parser.add_argument("--dashboards", action="store_true", help="Iniciar dashboards para cada nodo")

    args = parser.parse_args()

    test = LocalTest(num_nodes=args.nodes)
    test.setup()
    test.run_test(duration=args.duration, with_dashboards=args.dashboards)

if __name__ == "__main__":
    main()
