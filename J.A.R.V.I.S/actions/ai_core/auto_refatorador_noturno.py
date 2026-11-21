"""Action: auto_refatorador_noturno — auditoria noturna de testes, latencia e gargalos."""
from __future__ import annotations
from core.outcome import failed


def auto_refatorador_noturno(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._auto_refatorador_noturno_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("auto_refatorador_noturno", f"impl error: {e}")


TOOL = {
    "name": "auto_refatorador_noturno",
    "description": (
        "Analisa metricas de action_analytics.json, executa verificacao de testes e gera "
        "relatorio matinal com sugestoes de otimizacao sem alterar codigo automaticamente. "
        "Use para 'rodar auditoria noturna de codigo', 'gerar relatorio de performance das actions'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["analyze", "last_report", "run_tests"]},
            "slow_threshold_ms": {"type": "NUMBER", "description": "Limite de latencia em ms (padrao: 1500)"},
        },
        "required": [],
    },
    "handler": auto_refatorador_noturno,
    "tier": "core",
    "risk": "safe",
}