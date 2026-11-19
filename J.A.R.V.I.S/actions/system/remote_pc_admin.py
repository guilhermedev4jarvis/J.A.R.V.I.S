"""Action: remote_pc_admin."""
from __future__ import annotations
from core.outcome import failed

def remote_pc_admin(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._remote_pc_admin_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("remote_pc_admin", f"impl error: {e}")

TOOL = {
    "name": "remote_pc_admin",
    "description": ("Administração remota do PC: print da tela, top processos, reiniciar Windows, "
    "executar cmd/powershell com timeout. Também /tela /processos /reiniciar /cmd no Telegram."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["screenshot", "processes", "reboot", "cmd"]},
            "command": {"type": "STRING"},
            "text": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": remote_pc_admin,
    "tier": "core",
    "risk": "destructive",
}
