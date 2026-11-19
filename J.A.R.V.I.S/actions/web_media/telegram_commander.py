"""Action: telegram_commander — controle remoto via Telegram (chat autorizado)."""
from __future__ import annotations

from core.outcome import failed


def telegram_commander(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._telegram_commander_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("telegram_commander", f"impl error: {e}")


TOOL = {
    "name": "telegram_commander",
    "description": (
        "Listener Telegram para controle remoto 24/7. Comandos no chat autorizado: "
        "/cameras /status /falar <texto> /190 /demo. "
        "Actions: start | stop | status. Inicia sozinho no boot se TELEGRAM_BOT_TOKEN existir."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["start", "stop", "status"],
            },
        },
        "required": [],
    },
    "handler": telegram_commander,
    "tier": "core",
    "risk": "autonomous",
}
