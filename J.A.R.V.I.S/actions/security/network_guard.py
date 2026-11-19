"""Alias legacy tool `network_guard` → `network_manager` (mode=guard)."""
from __future__ import annotations

import actions.system.network_manager as _impl


def network_guard(parameters=None, **ctx):
    params = dict(parameters or {})
    params.setdefault("mode", "guard")
    params.setdefault("action", params.get("action") or "guard")
    return _impl(params, **ctx)


TOOL = {
    "name": "network_guard",
    "description": 'Alias → network_manager mode=guard',
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
    "handler": network_guard,
    "tier": "core",
    "risk": "review",
}
