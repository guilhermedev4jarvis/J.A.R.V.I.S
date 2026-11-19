
"""Action publica: extrator reader-mode de artigos."""
from __future__ import annotations

from core.outcome import failed
from ._extrator_artigo_web_impl import run as _run


def extrator_artigo_web(parameters=None, **ctx) -> str:
    try:
        return _run(parameters, **ctx)
    except Exception as e:
        return failed("extrator_artigo_web", str(e)[:240])


TOOL = {
    "name": "extrator_artigo_web",
    "description": (
        "Extrai artigo web em Markdown (trafilatura/bs4/html). "
        "USE para ler/salvar conteudo de URL publica. NAO USE para sites que exigem login."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "url": {"type": "STRING"},
            "salvar_na_memoria": {"type": "STRING"},
            "save": {"type": "STRING"},
            "categoria": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": extrator_artigo_web,
    "tier": "core",
    "risk": "safe",
}
