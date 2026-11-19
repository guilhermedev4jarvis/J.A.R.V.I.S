"""Action: mestre_feynman."""
from __future__ import annotations
from core.outcome import failed

def mestre_feynman(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._mestre_feynman_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("mestre_feynman", f"impl error: {e}")

TOOL = {
    "name": "mestre_feynman",
    "description": ("Método Feynman: sabatina sobre tema/arquivo, pergunta por pergunta, avalia lacunas."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["start", "answer", "end", "status"]},
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
    "handler": mestre_feynman,
    "tier": "core",
    "risk": "safe",
}
