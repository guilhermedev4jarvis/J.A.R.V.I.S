"""Action: anti_sabotagem_energia."""
from __future__ import annotations
from core.outcome import failed

def anti_sabotagem_energia(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._anti_sabotagem_energia_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("anti_sabotagem_energia", f"impl error: {e}")

TOOL = {
    "name": "anti_sabotagem_energia",
    "description": ("Monitor 24/7 de corte de energia (AC→bateria). Alerta Telegram. "
    "Actions: start | stop | status. Inicia no boot."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["start", "stop", "status"]},
            "text": {"type": "STRING"},
            "value": {"type": "STRING"},
            "minutes": {"type": "NUMBER"},
            "item": {"type": "STRING"},
            "category": {"type": "STRING"},
            "time": {"type": "STRING"},
            "command": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": anti_sabotagem_energia,
    "tier": "core",
    "risk": "safe",
}
