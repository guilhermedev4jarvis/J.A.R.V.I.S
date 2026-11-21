"""Action: cacador_assinaturas_esquecidas — detecta cobrancas recorrentes ociosas."""
from __future__ import annotations
from core.outcome import failed


def cacador_assinaturas_esquecidas(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._cacador_assinaturas_esquecidas_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("cacador_assinaturas_esquecidas", f"impl error: {e}")


TOOL = {
    "name": "cacador_assinaturas_esquecidas",
    "description": (
        "Analisa transacoes recorrentes no extrato bancario, cruza com habitos de uso reais "
        "e estima a economia anual ao cancelar assinaturas esquecidas. "
        "Use para 'cacar assinaturas esquecidas', 'verificar servicos recorrentes nao usados'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "min_months": {"type": "NUMBER", "description": "Minimo de meses repetidos (padrao: 2)"},
        },
        "required": [],
    },
    "handler": cacador_assinaturas_esquecidas,
    "tier": "core",
    "risk": "safe",
}