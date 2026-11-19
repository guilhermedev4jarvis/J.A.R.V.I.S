"""Action pública: cria skill por descrição."""
from __future__ import annotations

from core.outcome import failed
from ._criador_skill_por_voz_impl import run as _run


def criador_skill_por_voz(parameters=None, **ctx) -> str:
    try:
        return _run(parameters, **ctx)
    except Exception as e:
        return failed("criador_skill_por_voz", str(e)[:240])


TOOL = {
    "name": "criador_skill_por_voz",
    "description": (
        "Gera actions/<categoria>/<nome>.py e _impl a partir de descrição, "
        "valida AST/static_safety e tenta hot_reload."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "description": {"type": "STRING"},
            "query": {"type": "STRING"},
            "text": {"type": "STRING"},
            "name": {"type": "STRING"},
            "category": {"type": "STRING"},
            "overwrite": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": criador_skill_por_voz,
    "tier": "core",
    "risk": "review",
}
