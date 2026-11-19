"""Action pública: análise/limpeza de disco."""
from __future__ import annotations

from core.outcome import failed
from ._limpeza_profunda_disco_impl import run as _run


def limpeza_profunda_disco(parameters=None, **ctx) -> str:
    try:
        return _run(parameters, **ctx)
    except Exception as e:
        return failed("limpeza_profunda_disco", str(e)[:240])


TOOL = {
    "name": "limpeza_profunda_disco",
    "description": (
        "Escaneia TEMP e caches calculando MB liberáveis. "
        "mode=analisar (padrão) ou mode=limpar com confirm=sim."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {"type": "STRING"},
            "action": {"type": "STRING"},
            "confirm": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": limpeza_profunda_disco,
    "tier": "core",
    "risk": "review",
}
