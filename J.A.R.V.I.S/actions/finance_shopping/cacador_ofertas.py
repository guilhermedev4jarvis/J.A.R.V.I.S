"""Action: cacador_ofertas."""
from __future__ import annotations
from core.outcome import failed

def cacador_ofertas(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._cacador_ofertas_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("cacador_ofertas", f"impl error: {e}")

TOOL = {
    "name": "cacador_ofertas",
    "description": ("Radar de preços 24/7: vigiar preço de produto/passagem, listar ofertas. Notifica ao atingir meta."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["watch", "list", "remove", "start_worker", "stop_worker", "check_now"]},
            "text": {"type": "STRING"},
            "topic": {"type": "STRING"},
            "query": {"type": "STRING"},
            "value": {"type": "STRING"},
            "name": {"type": "STRING"},
            "mac": {"type": "STRING"},
            "language": {"type": "STRING"},
            "mode": {"type": "STRING"},
            "path": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": cacador_ofertas,
    "tier": "core",
    "risk": "autonomous",
}
