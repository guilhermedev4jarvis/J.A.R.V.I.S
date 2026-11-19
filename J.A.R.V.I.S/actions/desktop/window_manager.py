"""Alias legacy tool `window_manager` → `desktop_control` (mode=window)."""
from __future__ import annotations

from .desktop_control import desktop_control as _impl


def window_manager(parameters=None, **ctx):
    params = dict(parameters or {})
    params.setdefault("mode", "window")
    params.setdefault("action", params.get("action") or "window")
    return _impl(params, **ctx)


TOOL = {
    "name": "window_manager",
    "description": 'Alias → desktop_control mode=window',
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
    "handler": window_manager,
    "tier": "core",
    "risk": "review",
}
