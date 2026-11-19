
"""Action publica: historico e classificacao de precos."""
from __future__ import annotations

from core.outcome import failed
from ._comparador_preco_historico_impl import run as _run


def comparador_preco_historico(parameters=None, **ctx) -> str:
    try:
        return _run(parameters, **ctx)
    except Exception as e:
        return failed("comparador_preco_historico", str(e)[:240])


TOOL = {
    "name": "comparador_preco_historico",
    "description": (
        "Registra e analisa historico de precos em memory/precos_monitorados.json. "
        "action=registrar|analisar|listar|remover. Classifica oportunidade/media/maquiagem. "
        "NAO USE para cotacao de dolar (cotacao_dolar)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING"},
            "produto": {"type": "STRING"},
            "product": {"type": "STRING"},
            "preco": {"type": "NUMBER"},
            "price": {"type": "NUMBER"},
            "loja": {"type": "STRING"},
            "url": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": comparador_preco_historico,
    "tier": "core",
    "risk": "safe",
}
