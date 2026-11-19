"""Alias legacy tool `self_program` → `code_studio` (mode=self)."""
from __future__ import annotations

from .code_studio import code_studio as _impl


def self_program(parameters=None, **ctx):
    params = dict(parameters or {})
    params.setdefault("mode", "self")
    params.setdefault("action", params.get("action") or "self")
    return _impl(params, **ctx)


TOOL = {
    "name": "self_program",
    "description": 'Alias → code_studio mode=self',
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
    "handler": self_program,
    "tier": "core",
    "risk": "destructive",
}
