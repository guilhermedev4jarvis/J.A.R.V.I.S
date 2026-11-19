"""Action: controle_gastos."""
from __future__ import annotations
from core.outcome import failed

def controle_gastos(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._controle_gastos_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("controle_gastos", f"impl error: {e}")

TOOL = {
    "name": "controle_gastos",
    "description": ("Registro financeiro por voz em memory/gastos.csv. "
    "Anotar gasto, total do mês/semana. Também /gastos no Telegram."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["add", "summary", "month", "week"]},
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
    "handler": controle_gastos,
    "tier": "core",
    "risk": "safe",
}
