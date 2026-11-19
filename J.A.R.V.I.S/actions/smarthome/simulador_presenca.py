"""Action: simulador_presenca."""
from __future__ import annotations
from core.outcome import failed

def simulador_presenca(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._simulador_presenca_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("simulador_presenca", f"impl error: {e}")

TOOL = {
    "name": "simulador_presenca",
    "description": ("Simulador de presença (modo viagem): luzes e áudio discreto entre 18h30 e 23h30. "
    "Gatilhos: ativar/desativar simulador, /viagem."),
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
    "handler": simulador_presenca,
    "tier": "core",
    "risk": "autonomous",
}
