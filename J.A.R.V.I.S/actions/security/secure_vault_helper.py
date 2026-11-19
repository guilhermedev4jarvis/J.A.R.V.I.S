"""Action: secure_vault_helper — owner-gated secret copy with auto-clear clipboard."""
from __future__ import annotations
from core.outcome import failed

def secure_vault_helper(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._secure_vault_helper_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("secure_vault_helper", f"impl error: {e}")

TOOL = {
    "name": "secure_vault_helper",
    "description": (
        "Retrieve a named secret/token from the vault (core.secrets / config/secrets.vault) "
        "after owner_gate validation, copy it to the clipboard for a short TTL (default 15s) "
        "then auto-clear. Use for 'copia a chave da OpenAI', 'pega o token do cofre X'. "
        "Never speaks the secret value aloud."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["get", "copy", "list"]},
            "key": {"type": "STRING", "description": "Secret name"},
            "ttl": {"type": "NUMBER", "description": "Clipboard lifetime seconds (5-60, default 15)"},
        },
        "required": [],
    },
    "handler": secure_vault_helper,
    "tier": "core",
    "risk": "destructive",
}
