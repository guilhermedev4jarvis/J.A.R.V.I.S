"""Action: gravador_caixa_preta."""
from __future__ import annotations
from core.outcome import failed

def gravador_caixa_preta(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._gravador_caixa_preta_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("gravador_caixa_preta", f"impl error: {e}")

TOOL = {
    "name": "gravador_caixa_preta",
    "description": ("Gravação sigilosa de áudio em blocos de 5 min para memory/audit/gravacoes/ "
    "e envio ao Telegram. Gatilhos: ativar gravação sigilosa, parar gravação, /gravar."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["start", "stop", "status"]},
            "text": {"type": "STRING"},
            "value": {"type": "STRING"},
            "minutes": {"type": "NUMBER"},
            "item": {"type": "STRING"},
            "category": {"type": "STRING"},
            "time": {"type": "STRING"},
            "command": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": gravador_caixa_preta,
    "tier": "core",
    "risk": "review",
}
