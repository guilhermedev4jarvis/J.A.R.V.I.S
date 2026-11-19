"""Action pública: relatório semanal."""
from __future__ import annotations

from core.outcome import failed
from ._gerador_relatorio_semanal_impl import run as _run


def gerador_relatorio_semanal(parameters=None, **ctx) -> str:
    try:
        return _run(parameters, **ctx)
    except Exception as e:
        return failed("gerador_relatorio_semanal", str(e)[:240])


TOOL = {
    "name": "gerador_relatorio_semanal",
    "description": (
        "Consolida diario_cognitivo.jsonl, episodes.jsonl e gastos.csv "
        "em Markdown em memory/retrospectivas/."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "days": {"type": "INTEGER"},
            "action": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": gerador_relatorio_semanal,
    "tier": "core",
    "risk": "safe",
}
