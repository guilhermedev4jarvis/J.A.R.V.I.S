"""
hwmonitor_integration — hardware sensors readout (migrated; best-effort).
"""
from __future__ import annotations

import platform
from core.outcome import done, failed


def hwmonitor_integration(parameters: dict | None = None, **_ctx) -> str:
    params = parameters or {}
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory()
        facts = {
            "cpu_percent": cpu,
            "mem_percent": mem.percent,
            "platform": platform.system(),
        }
        try:
            temps = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else {}
            facts["temperatures"] = {k: [t.current for t in v[:3]] for k, v in (temps or {}).items()}
        except Exception:
            facts["temperatures"] = {}
        return done("hwmonitor_integration", **facts)
    except Exception as e:
        return failed("hwmonitor_integration", str(e))


_LEGACY_TOOL = {
    "name": "hwmonitor_integration",
    "description": "Leitura de CPU/memoria/temperaturas via psutil (ex-HWMonitor).",
    "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    "handler": hwmonitor_integration,
    "tier": "plugin",
    "risk": "safe",
}
