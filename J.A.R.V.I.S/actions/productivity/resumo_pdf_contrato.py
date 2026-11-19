"""Action pública: resumo de PDF/contrato."""
from __future__ import annotations

from core.outcome import failed
from ._resumo_pdf_contrato_impl import run as _run


def resumo_pdf_contrato(parameters=None, **ctx) -> str:
    try:
        return _run(parameters, **ctx)
    except Exception as e:
        return failed("resumo_pdf_contrato", str(e)[:240])


TOOL = {
    "name": "resumo_pdf_contrato",
    "description": (
        "Lê PDF local e resume partes, valores, datas, multas e pontos de atenção. path=arquivo.pdf"
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {"type": "STRING"},
            "file": {"type": "STRING"},
            "pdf": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": resumo_pdf_contrato,
    "tier": "core",
    "risk": "safe",
}
