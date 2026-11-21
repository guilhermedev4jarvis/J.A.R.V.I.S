"""Action: briefing_matinal_contexto — consolida clima, noticias, lembretes e e-mails."""
from __future__ import annotations
from core.outcome import failed


def briefing_matinal_contexto(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._briefing_matinal_contexto_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("briefing_matinal_contexto", f"impl error: {e}")


TOOL = {
    "name": "briefing_matinal_contexto",
    "description": (
        "Gera um resumo matinal consolidado de ate 60 segundos com previsao do tempo local, "
        "manchetes principais, lembretes pendentes e e-mails prioritarios. "
        "Use para 'briefing matinal', 'resumo do meu dia', 'o que temos para hoje'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "speak": {"type": "BOOLEAN", "description": "Se deve ler o briefing em voz alta (padrao: False)"},
        },
        "required": [],
    },
    "handler": briefing_matinal_contexto,
    "tier": "core",
    "risk": "safe",
}