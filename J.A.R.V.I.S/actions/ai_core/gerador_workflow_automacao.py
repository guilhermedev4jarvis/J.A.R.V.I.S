
"""Action publica: gerador de rotinas e gatilhos."""
from __future__ import annotations

from core.outcome import failed
from ._gerador_workflow_automacao_impl import run as _run


def gerador_workflow_automacao(parameters=None, **ctx) -> str:
    try:
        return _run(parameters, **ctx)
    except Exception as e:
        return failed("gerador_workflow_automacao", str(e)[:240])


TOOL = {
    "name": "gerador_workflow_automacao",
    "description": (
        "Compila rotinas/gatilhos a partir de descricao, valida actions no registry e "
        "salva em config/routines.json ou context_triggers.json. "
        "action=criar_rotina|criar_gatilho|listar|validar. USE dry_run=true para so validar."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING"},
            "descricao": {"type": "STRING"},
            "description": {"type": "STRING"},
            "nome_rotina": {"type": "STRING"},
            "name": {"type": "STRING"},
            "dry_run": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": gerador_workflow_automacao,
    "tier": "core",
    "risk": "review",
}
