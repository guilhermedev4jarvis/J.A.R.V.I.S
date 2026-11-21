"""Action: auditor_cftv_anomalias — detecta desvios estatisticos de movimento nas cameras."""
from __future__ import annotations
from core.outcome import failed


def auditor_cftv_anomalias(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._auditor_cftv_anomalias_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("auditor_cftv_anomalias", f"impl error: {e}")


TOOL = {
    "name": "auditor_cftv_anomalias",
    "description": (
        "Analisa logs historicos de eventos do CFTV para aprender padroes normais de horario "
        "e alertar sobre movimentacao atipica (ex: atividade na madrugada). "
        "Use para 'auditar anomalias das cameras', 'verificar movimento estranho hoje'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["audit", "baseline", "status"]},
            "window_hours": {"type": "NUMBER", "description": "Janela de analise em horas (padrao: 24)"},
        },
        "required": [],
    },
    "handler": auditor_cftv_anomalias,
    "tier": "core",
    "risk": "safe",
}