"""Action pública: diagnóstico de erros do PowerShell."""
from __future__ import annotations

from core.outcome import failed
from ._checagempowershell_impl import run as _run


def checagempowershell(parameters=None, **ctx) -> str:
    try:
        return _run(parameters, **ctx)
    except Exception as e:
        return failed("checagempowershell", str(e)[:240])


TOOL = {
    "name": "checagempowershell",
    "description": (
        "Diagnostica erros do PowerShell: histórico PSReadLine, logs Operational "
        "e análise de mensagem. mode=historico|logs_sistema|analisar_erro."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {"type": "STRING"},
            "action": {"type": "STRING"},
            "error": {"type": "STRING"},
            "text": {"type": "STRING"},
            "query": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": checagempowershell,
    "tier": "core",
    "risk": "safe",
}
