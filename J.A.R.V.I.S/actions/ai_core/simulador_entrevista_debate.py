"""Action pública: simulador de entrevista/debate."""
from __future__ import annotations

from core.outcome import failed
from ._simulador_entrevista_debate_impl import run as _run


def simulador_entrevista_debate(parameters=None, **ctx) -> str:
    try:
        return _run(parameters, **ctx)
    except Exception as e:
        return failed("simulador_entrevista_debate", str(e)[:240])


TOOL = {
    "name": "simulador_entrevista_debate",
    "description": (
        "Treino interativo: entrevista, debate ou apresentação. "
        "action=iniciar|responder|finalizar; kind=entrevista|debate|apresentacao."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING"},
            "mode": {"type": "STRING"},
            "kind": {"type": "STRING"},
            "tipo": {"type": "STRING"},
            "message": {"type": "STRING"},
            "text": {"type": "STRING"},
            "query": {"type": "STRING"},
            "session_id": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": simulador_entrevista_debate,
    "tier": "core",
    "risk": "safe",
}
