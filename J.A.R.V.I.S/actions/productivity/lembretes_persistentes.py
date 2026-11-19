"""Action: lembretes_persistentes."""
from __future__ import annotations
from core.outcome import failed

def lembretes_persistentes(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._lembretes_persistentes_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("lembretes_persistentes", f"impl error: {e}")

TOOL = {
    "name": "lembretes_persistentes",
    "description": ("Lembretes persistentes (remédios/contas) com TTS + Telegram até confirmação. "
    "Actions: add | list | confirm | start_scheduler."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["add", "list", "confirm", "start_scheduler", "stop_scheduler"]},
            "text": {"type": "STRING"},
            "value": {"type": "STRING"},
            "minutes": {"type": "NUMBER"},
            "item": {"type": "STRING"},
            "category": {"type": "STRING"},
            "time": {"type": "STRING"},
            "command": {"type": "STRING"},
            "query": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": lembretes_persistentes,
    "tier": "core",
    "risk": "safe",
}
