"""Alias legacy tool `resource_governor` → `system_monitor` (mode=governor)."""
from __future__ import annotations

from .system_health import system_health as _impl


def resource_governor(parameters=None, **ctx):
    params = dict(parameters or {})
    params.setdefault("mode", "governor")
    params.setdefault("action", params.get("action") or "governor")
    return _impl(params, **ctx)


TOOL = {
    "name": "resource_governor",
    "description": 'Alias → system_health mode=governor',
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
    "handler": resource_governor,
    "tier": "core",
    "risk": "review",
}
