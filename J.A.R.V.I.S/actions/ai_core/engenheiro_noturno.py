"""Action: engenheiro_noturno."""
from __future__ import annotations
from core.outcome import failed

def engenheiro_noturno(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._engenheiro_noturno_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("engenheiro_noturno", f"impl error: {e}")

TOOL = {
    "name": "engenheiro_noturno",
    "description": ("Diagnóstico noturno: pytest, dependency_health, limpeza de temporários, relatório Telegram. "
    "Agenda 02:30 ou execução imediata."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["run_now", "start_scheduler", "stop_scheduler", "status"]},
            "text": {"type": "STRING"},
            "topic": {"type": "STRING"},
            "query": {"type": "STRING"},
            "value": {"type": "STRING"},
            "name": {"type": "STRING"},
            "mac": {"type": "STRING"},
            "path": {"type": "STRING"},
            "details": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": engenheiro_noturno,
    "tier": "core",
    "risk": "review",
}
