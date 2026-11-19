"""Action: modo_foco."""
from __future__ import annotations
from core.outcome import failed

def modo_foco(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._modo_foco_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("modo_foco", f"impl error: {e}")

TOOL = {
    "name": "modo_foco",
    "description": ("Modo foco: minimiza distrações e agenda anúncio ao fim do período. "
    "Gatilhos: ativar modo foco por X minutos, encerrar modo foco."),
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
            "query": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": modo_foco,
    "tier": "core",
    "risk": "safe",
}
