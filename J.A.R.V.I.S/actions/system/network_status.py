"""Alias legacy tool `network_status` → `network_manager` (mode=status)."""
from __future__ import annotations

from .network_manager import network_manager as _impl


def network_status(parameters=None, **ctx):
    params = dict(parameters or {})
    params.setdefault("mode", "status")
    params.setdefault("action", params.get("action") or "status")
    return _impl(params, **ctx)


TOOL = {
    "name": "network_status",
    "description": 'Alias → network_manager mode=status',
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
    "handler": network_status,
    "tier": "core",
    "risk": "safe",
}
