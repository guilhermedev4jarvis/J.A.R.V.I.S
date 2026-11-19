"""Action: diario_cognitivo."""
from __future__ import annotations
from core.outcome import failed

def diario_cognitivo(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._diario_cognitivo_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("diario_cognitivo", f"impl error: {e}")

TOOL = {
    "name": "diario_cognitivo",
    "description": ("Diário cognitivo / segunda mente: registrar pensamento, anotar no diário, resumo da semana. "
    "Persiste em memory/diario_cognitivo.jsonl com tema e sentimento."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["add", "summary_week", "list", "start_scheduler"]},
            "text": {"type": "STRING"},
            "topic": {"type": "STRING"},
            "query": {"type": "STRING"},
            "value": {"type": "STRING"},
            "name": {"type": "STRING"},
            "mac": {"type": "STRING"},
            "language": {"type": "STRING"},
            "mode": {"type": "STRING"},
            "path": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": diario_cognitivo,
    "tier": "core",
    "risk": "safe",
}
