"""Action: bloqueador_intruso_rede — identifica e isola dispositivos desconhecidos no Wi-Fi."""
from __future__ import annotations
from core.outcome import failed


def bloqueador_intruso_rede(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._bloqueador_intruso_rede_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("bloqueador_intruso_rede", f"impl error: {e}")


TOOL = {
    "name": "bloqueador_intruso_rede",
    "description": (
        "Cruza dispositivos conectados na rede Wi-Fi contra a whitelist em network_guard.json "
        "e permite listar ou bloquear intrusos mediante confirmacao explicita. "
        "Use para 'verificar intrusos no wifi', 'bloquear dispositivo desconhecido na rede'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["scan", "quarantine", "release", "status"]},
            "target_mac": {"type": "STRING", "description": "Endereco MAC do dispositivo alvo"},
            "target_ip": {"type": "STRING", "description": "Endereco IP do dispositivo alvo"},
            "confirmed": {"type": "BOOLEAN", "description": "Confirmacao explicita para aplicar bloqueio"},
        },
        "required": [],
    },
    "handler": bloqueador_intruso_rede,
    "tier": "core",
    "risk": "destructive",
}