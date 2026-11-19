"""Action: lista_compras."""
from __future__ import annotations
from core.outcome import failed

def lista_compras(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._lista_compras_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("lista_compras", f"impl error: {e}")

TOOL = {
    "name": "lista_compras",
    "description": ("Lista de compras sincronizada (memory/lista_compras.json). "
    "Adicionar item, ler lista, limpar. Também /lista no Telegram."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["add", "list", "clear", "remove"]},
            "text": {"type": "STRING"},
            "value": {"type": "STRING"},
            "minutes": {"type": "NUMBER"},
            "item": {"type": "STRING"},
            "category": {"type": "STRING"},
            "time": {"type": "STRING"},
            "command": {"type": "STRING"},
            "query": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": lista_compras,
    "tier": "core",
    "risk": "safe",
}
