"""Action: sentinel_patrol — ronda noturna, modo encomenda e modo ausente (iCSee)."""
from __future__ import annotations

from core.outcome import failed


def sentinel_patrol(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._sentinel_patrol_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("sentinel_patrol", f"impl error: {e}")


TOOL = {
    "name": "sentinel_patrol",
    "description": (
        "Vigilância proativa com câmeras iCSee em background. Use para: "
        "'ativar ronda noturna', 'iniciar sentinel', 'parar ronda', "
        "'estou esperando uma entrega', 'vigiar portão' (modo encomenda), "
        "'estou saindo de casa', 'ativar modo ausente'. "
        "Actions: start_night | start_delivery | start_away | stop | status."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["start_night", "start_delivery", "start_away", "stop", "status", "analisar"],
                "description": "Modo de patrulha ou stop/status",
            },
            "mode": {
                "type": "STRING",
                "description": "Alias: night|delivery|away|stop",
            },
        },
        "required": [],
    },
    "handler": sentinel_patrol,
    "tier": "core",
    "risk": "autonomous",
}
