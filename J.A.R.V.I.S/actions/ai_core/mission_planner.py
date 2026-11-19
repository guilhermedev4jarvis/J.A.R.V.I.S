"""Action: mission_planner — autonomous multi-tool mission planner and executor."""
from __future__ import annotations

from core.outcome import failed


def mission_planner(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._mission_planner_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("mission_planner", f"impl error: {e}")


TOOL = {
    "name": "mission_planner",
    "description": (
        "Agente autonomo de tarefas em cadeia. Use SEMPRE que o usuario pedir um "
        "objetivo composto que exige 2 ou mais tools em sequencia "
        "(ex: pesquisar + salvar arquivo + avisar no WhatsApp). "
        "Modes: plan_and_run (planeja e executa), plan_only (so gera o plano), "
        "resume (retoma missao), status/list, cancel. "
        "Planos ficam em memory/desktop_missions/. Max 8 etapas. "
        "Etapas sensiveis passam por owner_gate. "
        "NAO use para tarefas de 1 passo — use a tool direta."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "plan_and_run | plan_only | resume | status | list | cancel",
                "enum": ["plan_and_run", "plan_only", "resume", "status", "list", "cancel"],
            },
            "goal": {
                "type": "STRING",
                "description": "Objetivo em linguagem natural da missao",
            },
            "mission_id": {
                "type": "STRING",
                "description": "Id da missao para resume/status/cancel",
            },
        },
        "required": [],
    },
    "handler": mission_planner,
    "tier": "core",
    "risk": "autonomous",
}
