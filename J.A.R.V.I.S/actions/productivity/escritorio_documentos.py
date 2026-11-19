"""Action: escritorio_documentos."""
from __future__ import annotations
from core.outcome import failed

def escritorio_documentos(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._escritorio_documentos_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("escritorio_documentos", f"impl error: {e}")

TOOL = {
    "name": "escritorio_documentos",
    "description": ("Gera contrato/recibo/currículo/documento em DOCX/PDF por voz; salva e envia no Telegram."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["generate"]},
            "text": {"type": "STRING"},
            "topic": {"type": "STRING"},
            "query": {"type": "STRING"},
            "value": {"type": "STRING"},
            "name": {"type": "STRING"},
            "mac": {"type": "STRING"},
            "path": {"type": "STRING"},
            "details": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": escritorio_documentos,
    "tier": "core",
    "risk": "safe",
}
