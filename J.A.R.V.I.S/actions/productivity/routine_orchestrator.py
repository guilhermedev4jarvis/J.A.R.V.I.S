"""Action: routine_orchestrator — create/list/run command macros (routines)."""
from __future__ import annotations

from core.outcome import failed


def routine_orchestrator(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._routine_orchestrator_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("routine_orchestrator", f"impl error: {e}")


TOOL = {
    "name": "routine_orchestrator",
    "description": (
        "Create, list, edit and run saved multi-step routines/macros from "
        "config/routines.json. Use for 'ativar modo trabalho', 'rodar rotina X', "
        "'listar rotinas'. Each step can call another tool and speak progress via TTS."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "list | get | create | delete | run",
                "enum": ["list", "get", "create", "delete", "run"],
            },
            "name": {"type": "STRING", "description": "Routine name"},
            "description": {"type": "STRING"},
            "steps": {"type": "STRING", "description": "JSON list of {tool, params, speak}"},
        },
        "required": [],
    },
    "handler": routine_orchestrator,
    "tier": "core",
    "risk": "autonomous",
}
