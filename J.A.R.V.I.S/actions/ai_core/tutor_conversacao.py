"""Action: tutor_conversacao."""
from __future__ import annotations
from core.outcome import failed

def tutor_conversacao(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._tutor_conversacao_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("tutor_conversacao", f"impl error: {e}")

TOOL = {
    "name": "tutor_conversacao",
    "description": ("Tutor de idiomas e entrevistas: modo treino de inglês/espanhol, simular entrevista, encerrar treino."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["start", "turn", "end", "status"]},
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
    "handler": tutor_conversacao,
    "tier": "core",
    "risk": "safe",
}
