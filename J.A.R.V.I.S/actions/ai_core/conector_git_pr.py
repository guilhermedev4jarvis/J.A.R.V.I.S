"""Action: conector_git_pr — cria branches isoladas, commits semanticos e rollback seguro."""
from __future__ import annotations
from core.outcome import failed


def conector_git_pr(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._conector_git_pr_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("conector_git_pr", f"impl error: {e}")


TOOL = {
    "name": "conector_git_pr",
    "description": (
        "Gerencia branches isoladas (jarvis/auto-<timestamp>), commits semanticos e rollback "
        "seguro para auto-modificacoes do codigo do J.A.R.V.I.S. "
        "Use para 'criar branch de experimento', 'salvar checkpoint git', 'fazer rollback do codigo'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["status", "create_branch", "commit", "rollback"]},
            "message": {"type": "STRING", "description": "Mensagem do commit semantico"},
            "confirmed": {"type": "BOOLEAN", "description": "Confirmacao explicita para rollback"},
        },
        "required": [],
    },
    "handler": conector_git_pr,
    "tier": "core",
    "risk": "destructive",
}