"""Alias legacy tool `hwmonitor_integration` → `system_monitor` (mode=hardware_sensors)."""
from __future__ import annotations

from .system_health import system_health as _impl


def hwmonitor_integration(parameters=None, **ctx):
    params = dict(parameters or {})
    params.setdefault("mode", "hardware_sensors")
    params.setdefault("action", params.get("action") or "hardware_sensors")
    return _impl(params, **ctx)


TOOL = {
    "name": "hwmonitor_integration",
    "description": 'Alias → system_health mode=hardware_sensors',
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {"type": "STRING"},
            "action": {"type": "STRING"},
            "query": {"type": "STRING"},
            "path": {"type": "STRING"},
            "command": {"type": "STRING"},
            "topic": {"type": "STRING"},
            "value": {"type": "STRING"},
            "goal": {"type": "STRING"},
            "prompt": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": hwmonitor_integration,
    "tier": "core",
    "risk": "safe",
}
