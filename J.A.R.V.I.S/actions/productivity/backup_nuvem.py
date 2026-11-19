"""Action: backup_nuvem."""
from __future__ import annotations
from core.outcome import failed

def backup_nuvem(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._backup_nuvem_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("backup_nuvem", f"impl error: {e}")

TOOL = {
    "name": "backup_nuvem",
    "description": ("Backup da pasta memory/ em zip enviado ao Telegram. "
    "Gatilhos: fazer backup agora, /backup; agenda domingo 03:00 no boot."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["now", "start_scheduler", "stop_scheduler", "status"]},
            "command": {"type": "STRING"},
            "text": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": backup_nuvem,
    "tier": "core",
    "risk": "review",
}
