
"""Action publica: auditoria de senhas/e-mails sem vazar segredo."""
from __future__ import annotations

from core.outcome import failed
from ._auditor_vazamento_credenciais_impl import run as _run


def auditor_vazamento_credenciais(parameters=None, **ctx) -> str:
    try:
        return _run(parameters, **ctx)
    except Exception as e:
        return failed("auditor_vazamento_credenciais", str(e)[:240])


TOOL = {
    "name": "auditor_vazamento_credenciais",
    "description": (
        "Audita senha via k-anonymity SHA-1 (HIBP range API) ou forca local; "
        "nunca loga senha em claro. mode=verificar_senha|auditar_forca|verificar_email. "
        "NAO USE para armazenar senhas (use secure_vault_helper)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {"type": "STRING"},
            "action": {"type": "STRING"},
            "password": {"type": "STRING"},
            "senha": {"type": "STRING"},
            "email": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": auditor_vazamento_credenciais,
    "tier": "core",
    "risk": "safe",
}
