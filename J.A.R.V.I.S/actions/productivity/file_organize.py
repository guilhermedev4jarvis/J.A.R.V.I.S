"""Alias legacy tool `file_organize` → `file_manager` (mode=organize)."""
from __future__ import annotations

from .file_manager import file_manager as _impl


def file_organize(parameters=None, **ctx):
    params = dict(parameters or {})
    params.setdefault("mode", "organize")
    params.setdefault("action", params.get("action") or "organize")
    return _impl(params, **ctx)


TOOL = {
    "name": "file_organize",
    "description": "Organiza arquivos existentes por tipo/data. USE para arrumar Downloads/Desktop. NAO USE para mover um arquivo especifico (mover_downloads) nem baixar da internet.",
    
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
    "handler": file_organize,
    "tier": "core",
    "risk": "review",
}
