"""Action: protocolo_dissuasao."""
from __future__ import annotations
from core.outcome import failed

def protocolo_dissuasao(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._protocolo_dissuasao_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("protocolo_dissuasao", f"impl error: {e}")

TOOL = {
    "name": "protocolo_dissuasao",
    "description": ("Modo dissuasão/intimidação: volume máximo, luzes Tuya, alerta vocal firme e sirene. "
    "Gatilhos: ativar modo dissuasão, espantar intruso, /dissuasao."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["ativar", "parar", "status"]},
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
    "handler": protocolo_dissuasao,
    "tier": "core",
    "risk": "destructive",
}
