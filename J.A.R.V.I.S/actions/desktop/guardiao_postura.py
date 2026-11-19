"""Action: guardiao_postura."""
from __future__ import annotations
from core.outcome import failed

def guardiao_postura(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._guardiao_postura_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("guardiao_postura", f"impl error: {e}")

TOOL = {
    "name": "guardiao_postura",
    "description": ("Monitor de postura/ergonomia via webcam a cada 25 min; lembrete TTS discreto; apaga frame."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["start", "stop", "status"]},
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
    "handler": guardiao_postura,
    "tier": "core",
    "risk": "safe",
}
