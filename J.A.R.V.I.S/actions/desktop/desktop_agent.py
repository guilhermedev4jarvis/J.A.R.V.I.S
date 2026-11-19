"""Alias legacy tool `desktop_agent` → `desktop_control` (mode=agent)."""
from __future__ import annotations

from .desktop_control import desktop_control as _impl


def desktop_agent(parameters=None, **ctx):
    params = dict(parameters or {})
    params.setdefault("mode", "agent")
    params.setdefault("action", params.get("action") or "agent")
    return _impl(params, **ctx)


TOOL = {
    "name": "desktop_agent",
    "description": 'Alias → desktop_control mode=agent',
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
    "handler": desktop_agent,
    "tier": "core",
    "risk": "autonomous",
}
