"""Action: daily_ops — briefing matinal, watchdog de internet e memória visual."""
from __future__ import annotations

from core.outcome import failed


def daily_ops(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._daily_ops_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("daily_ops", f"impl error: {e}")


TOOL = {
    "name": "daily_ops",
    "description": (
        "Operações diárias 24/7: 'bom dia', 'resumo do dia' (briefing: clima Rio Preto, "
        "notícias, e-mails/lembretes); watchdog de internet; memória visual "
        "('onde está minha X?', 'memorizar onde deixei X'). "
        "Actions: briefing | watchdog_start | watchdog_stop | watchdog_status | "
        "memorize_object | find_object."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": [
                    "briefing",
                    "watchdog_start",
                    "watchdog_stop",
                    "watchdog_status",
                    "memorize_object",
                    "find_object",
                ],
            },
            "object": {"type": "STRING", "description": "Nome do objeto para memória visual"},
            "query": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": daily_ops,
    "tier": "core",
    "risk": "safe",
}
