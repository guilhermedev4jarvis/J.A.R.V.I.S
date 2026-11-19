"""Action: webhook_bridge — named webhooks for IoT and mobile notifications."""
from __future__ import annotations
from core.outcome import failed

def webhook_bridge(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._webhook_bridge_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("webhook_bridge", f"impl error: {e}")

TOOL = {
    "name": "webhook_bridge",
    "description": (
        "Ponte de webhooks nomeados (Home Assistant, ntfy, Discord, Telegram). "
        "Modes: trigger, register, list, remove. Valida URL (anti-SSRF), "
        "owner_gate em envios, credenciais via secrets {{secret:name}}. "
        "Use for 'dispara alerta no celular', 'liga a luz do quarto via webhook'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["trigger", "register", "list", "remove"],
            },
            "name": {"type": "STRING"},
            "url": {"type": "STRING"},
            "method": {"type": "STRING"},
            "message": {"type": "STRING"},
            "body_template": {"type": "STRING"},
            "allow_private_hosts": {"type": "STRING"},
            "requires_owner_gate": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": webhook_bridge,
    "tier": "core",
    "risk": "destructive",
}
