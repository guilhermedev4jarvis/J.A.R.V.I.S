"""Action pública: traduz texto na tela."""
from __future__ import annotations

from core.outcome import failed
from ._tradutor_tela_instantaneo_impl import run as _run


def tradutor_tela_instantaneo(parameters=None, **ctx) -> str:
    try:
        return _run(parameters, **ctx)
    except Exception as e:
        return failed("tradutor_tela_instantaneo", str(e)[:240])


TOOL = {
    "name": "tradutor_tela_instantaneo",
    "description": (
        "Captura tela/janela, OCR e traduz para o idioma pedido (padrão pt-BR)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "lang": {"type": "STRING"},
            "target": {"type": "STRING"},
            "text": {"type": "STRING"},
            "action": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": tradutor_tela_instantaneo,
    "tier": "core",
    "risk": "safe",
}
