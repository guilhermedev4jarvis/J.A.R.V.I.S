"""Action: radar_dispositivos_wifi."""
from __future__ import annotations
from core.outcome import failed

def radar_dispositivos_wifi(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._radar_dispositivos_wifi_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("radar_dispositivos_wifi", f"impl error: {e}")

TOOL = {
    "name": "radar_dispositivos_wifi",
    "description": ("Varredura da rede local: quem está no wi-fi, alerta de novos dispositivos, registrar MAC."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["scan", "list_known", "register", "start_alert", "stop_alert", "status"]},
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
    "handler": radar_dispositivos_wifi,
    "tier": "core",
    "risk": "review",
}
