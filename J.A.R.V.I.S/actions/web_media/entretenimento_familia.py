"""Action: entretenimento_familia."""
from __future__ import annotations
from core.outcome import failed

def entretenimento_familia(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._entretenimento_familia_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("entretenimento_familia", f"impl error: {e}")

TOOL = {
    "name": "entretenimento_familia",
    "description": ("Quiz em família e curiosidades históricas. Gatilhos: vamos jogar perguntas e respostas, "
    "iniciar quiz, conta uma curiosidade, placar do jogo."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["start_quiz", "answer", "curiosity", "score", "end"]},
            "text": {"type": "STRING"},
            "name": {"type": "STRING"},
            "plate": {"type": "STRING"},
            "query": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": entretenimento_familia,
    "tier": "core",
    "risk": "safe",
}
