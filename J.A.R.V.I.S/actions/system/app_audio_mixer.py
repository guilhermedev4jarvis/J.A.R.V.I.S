"""Action: app_audio_mixer — per-app mute/volume (Windows/pycaw)."""
from __future__ import annotations
from core.outcome import failed

def app_audio_mixer(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._app_audio_mixer_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("app_audio_mixer", f"impl error: {e}")

TOOL = {
    "name": "app_audio_mixer",
    "description": (
        "List processes with audio and mute/unmute/set volume 0-100% per application "
        "on Windows (pycaw). Use for 'muta o Discord', 'Chrome em 20%', 'lista áudio dos apps'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["list", "mute", "unmute", "volume"]},
            "app": {"type": "STRING", "description": "Process/app name fragment"},
            "volume": {"type": "NUMBER", "description": "0-100"},
        },
        "required": [],
    },
    "handler": app_audio_mixer,
    "tier": "core",
    "risk": "review",
}
