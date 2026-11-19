
"""Action publica: monitor de mudancas em paginas web."""
from __future__ import annotations

from core.outcome import failed
from ._monitor_mudanca_pagina_impl import run as _run


def monitor_mudanca_pagina(parameters=None, **ctx) -> str:
    try:
        return _run(parameters, **ctx)
    except Exception as e:
        return failed("monitor_mudanca_pagina", str(e)[:240])


TOOL = {
    "name": "monitor_mudanca_pagina",
    "description": (
        "Vigia URLs publicas e detecta mudancas por hash SHA-256 + diff. "
        "action=adicionar|verificar|verificar_todos|remover|listar. "
        "Bloqueia localhost/IPs privados (SSRF). NAO USE para login em sites."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING"},
            "url": {"type": "STRING"},
            "alias": {"type": "STRING"},
            "name": {"type": "STRING"},
            "css_selector": {"type": "STRING"},
            "selector": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": monitor_mudanca_pagina,
    "tier": "core",
    "risk": "safe",
}
