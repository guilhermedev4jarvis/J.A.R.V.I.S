"""
JARVIS plugin: system_resources_monitor
Versão completa - CPU, RAM, GPU, Disco, Rede + Top processos
Funciona sem HWMonitor (temperaturas são opcionais)
"""
from __future__ import annotations

import platform
import subprocess
import time
from typing import Optional

def _get_gpu_nvidia() -> tuple[Optional[float], Optional[float]]:
    """Retorna (utilização %, temperatura °C) da GPU NVIDIA."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            util, temp = result.stdout.strip().split(",")
            return float(util.strip()), float(temp.strip())
    except Exception:
        pass
    return None, None


def _get_temps_wmi() -> dict[str, float]:
    """Tenta ler temperaturas via WMI (só funciona se OpenHardwareMonitor estiver rodando)."""
    temps = {}
    if platform.system() != "Windows":
        return temps
    try:
        import wmi  # type: ignore
        w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
        for sensor in w.Sensor():
            if sensor.SensorType == "Temperature" and sensor.Value is not None:
                name = (sensor.Name or "").lower()
                value = float(sensor.Value)
                if "cpu" in name or "package" in name or "core" in name:
                    temps.setdefault("cpu", value)
                elif "gpu" in name:
                    temps.setdefault("gpu", value)
    except Exception:
        pass
    return temps


def _get_network_speed(interval: float = 1.0) -> tuple[float, float]:
    """Retorna (download KB/s, upload KB/s) medindo por 1 segundo."""
    try:
        net1 = psutil.net_io_counters()
        time.sleep(interval)
        net2 = psutil.net_io_counters()
        download = (net2.bytes_recv - net1.bytes_recv) / 1024 / interval
        upload = (net2.bytes_sent - net1.bytes_sent) / 1024 / interval
        return download, upload
    except Exception:
        return 0.0, 0.0


def _get_top_processes(limit: int = 3) -> list[str]:
    """Retorna os processos que mais consomem CPU e RAM."""
    processes = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                if info['cpu_percent'] is None:
                    info['cpu_percent'] = 0.0
                if info['memory_percent'] is None:
                    info['memory_percent'] = 0.0
                processes.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Ordena por CPU e depois por RAM
        processes.sort(key=lambda p: (p['cpu_percent'], p['memory_percent']), reverse=True)
        
        top = []
        for p in processes[:limit]:
            name = p['name'] or "desconhecido"
            cpu = p['cpu_percent']
            mem = p['memory_percent']
            top.append(f"{name} ({cpu:.0f}% CPU, {mem:.1f}% RAM)")
        return top
    except Exception:
        return []


def run(parameters: dict, player=None, session_memory=None) -> str:
    """
    Retorna uma frase natural sobre o estado atual do sistema.
    """
    try:
        global psutil
        import psutil

        # === CPU ===
        cpu = psutil.cpu_percent(interval=0.5)

        # === RAM ===
        mem = psutil.virtual_memory()
        ram = mem.percent
        ram_used = mem.used / (1024 ** 3)
        ram_total = mem.total / (1024 ** 3)

        # === Disco (partição principal) ===
        disk = psutil.disk_usage('/')
        if platform.system() == "Windows":
            disk = psutil.disk_usage('C:\\')
        disk_percent = disk.percent
        disk_used = disk.used / (1024 ** 3)
        disk_total = disk.total / (1024 ** 3)

        # === Rede ===
        download, upload = _get_network_speed(interval=0.8)

        # === GPU ===
        gpu_util, gpu_temp_nvidia = _get_gpu_nvidia()

        # === Temperaturas (opcional) ===
        temps = _get_temps_wmi()
        cpu_temp = temps.get("cpu")
        gpu_temp = temps.get("gpu") or gpu_temp_nvidia

        # === Top processos ===
        top_procs = _get_top_processes(limit=3)

        # ========== Monta a resposta ==========
        parts = [
            f"CPU em {cpu:.0f}%",
            f"RAM em {ram:.0f}% ({ram_used:.1f} de {ram_total:.1f} GB)",
            f"Disco em {disk_percent:.0f}% ({disk_used:.0f} de {disk_total:.0f} GB)"
        ]

        # Rede
        if download > 10 or upload > 10:  # só fala se tiver tráfego relevante
            parts.append(f"rede baixando a {download:.0f} KB/s e enviando a {upload:.0f} KB/s")
        else:
            parts.append("rede praticamente parada")

        # GPU
        if gpu_util is not None:
            parts.append(f"GPU em {gpu_util:.0f}%")
        else:
            parts.append("não detectei GPU NVIDIA")

        # Temperaturas (só se conseguir ler)
        if cpu_temp is not None:
            parts.append(f"CPU a {cpu_temp:.0f}°C")
        if gpu_temp is not None:
            parts.append(f"GPU a {gpu_temp:.0f}°C")

        # Top processos
        if top_procs:
            procs_text = ", ".join(top_procs)
            parts.append(f"processos que mais consomem: {procs_text}")

        # Frase final natural
        if len(parts) <= 2:
            return f"Sir, {' e '.join(parts)}."
        else:
            return f"Sir, {', '.join(parts[:-1])} e {parts[-1]}."

    except Exception as e:
        return f"Sir, o plugin system_resources_monitor falhou: {e}"

# ── Unified action contract (migrated from plugins/) ──────────────────────────

def system_resources_monitor(parameters=None, player=None, session_memory=None, **_ctx):
    """_LEGACY_TOOL handler — delegates to legacy run()."""
    params = parameters if isinstance(parameters, dict) else {}
    try:
        return run(params, player=player, session_memory=session_memory)
    except TypeError:
        try:
            return run(params, player=player)
        except TypeError:
            return run(params)


_LEGACY_TOOL = {
    "name": "system_resources_monitor",
    "description": ('Mostra carga de CPU, RAM, GPU, uso de disco, velocidade da rede  e os processos que mais consomem recursos.'),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": []
    },
    "handler": system_resources_monitor,
    "tier": "plugin",
    "risk": "review",
}
