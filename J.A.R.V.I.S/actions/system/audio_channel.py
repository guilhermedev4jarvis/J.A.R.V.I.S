"""Action: audio_channel — alterna escuta local (casa) vs Telegram vs híbrido."""
from __future__ import annotations

from core.outcome import failed


def audio_channel(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._audio_channel_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("audio_channel", f"impl error: {e}")


TOOL = {
    "name": "audio_channel",
    "description": (
        "Alterna o canal de áudio do J.A.R.V.I.S.: modo casa (microfone local/AudioRelay), "
        "modo rua/telegram (só Bot) ou híbrido. "
        "Gatilhos: 'alternar áudio para o Telegram', 'modo rua', 'pausar microfone local', "
        "'voltar áudio para a casa', '/modo_rua', '/modo_casa', '/audio_hibrido'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["set", "status", "casa", "telegram", "hibrido", "rua"],
            },
            "mode": {
                "type": "STRING",
                "description": "casa | telegram | hibrido",
            },
        },
        "required": [],
    },
    "handler": audio_channel,
    "tier": "core",
    "risk": "safe",
}
