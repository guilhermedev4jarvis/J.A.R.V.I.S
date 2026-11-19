"""Action: curador_nicho."""
from __future__ import annotations
from core.outcome import failed

def curador_nicho(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._curador_nicho_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("curador_nicho", f"impl error: {e}")

TOOL = {
    "name": "curador_nicho",
    "description": ("Curadoria de notícias por nicho: acompanhar tópico, boletim executivo curto."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["follow", "list", "bulletin", "unfollow"]},
            "text": {"type": "STRING"},
            "topic": {"type": "STRING"},
            "query": {"type": "STRING"},
            "value": {"type": "STRING"},
            "name": {"type": "STRING"},
            "mac": {"type": "STRING"},
            "path": {"type": "STRING"},
            "details": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": curador_nicho,
    "tier": "core",
    "risk": "safe",
}
