"""Action: smart_home — Tuya/Smart Life lights + Wake-on-LAN."""
from __future__ import annotations

from core.outcome import failed


def smart_home(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._smart_home_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("smart_home", f"impl error: {e}")


TOOL = {
    "name": "smart_home",
    "description": (
        "Casa inteligente local: ligar/desligar luz [cômodo], apagar todas as luzes, "
        "modo cinema (Tuya/Smart Life via tinytuya). Também Wake-on-LAN: "
        "'acordar meu pc', 'ligar computador [nome]'. "
        "Actions: light_on | light_off | lights_off_all | cinema | wol | status."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["light_on", "light_off", "lights_off_all", "cinema", "wol", "status"],
            },
            "room": {"type": "STRING", "description": "Cômodo da luz"},
            "device": {"type": "STRING", "description": "Nome do PC para WoL"},
            "state": {"type": "STRING", "description": "on|off"},
        },
        "required": [],
    },
    "handler": smart_home,
    "tier": "core",
    "risk": "review",
}
