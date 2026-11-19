"""Action: controle_media_casa."""
from __future__ import annotations
from core.outcome import failed

def controle_media_casa(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._controle_media_casa_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("controle_media_casa", f"impl error: {e}")

TOOL = {
    "name": "controle_media_casa",
    "description": ("Controle de mídia e volume: aumentar/diminuir volume, mutar, pausar, próxima, "
    "abrir youtube [busca]. Usa teclas de mídia do sistema."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["volume_up", "volume_down", "mute", "unmute", "play_pause", "next", "previous", "youtube", "spotify"]},
            "text": {"type": "STRING"},
            "value": {"type": "STRING"},
            "minutes": {"type": "NUMBER"},
            "item": {"type": "STRING"},
            "category": {"type": "STRING"},
            "time": {"type": "STRING"},
            "command": {"type": "STRING"},
            "query": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": controle_media_casa,
    "tier": "core",
    "risk": "safe",
}
