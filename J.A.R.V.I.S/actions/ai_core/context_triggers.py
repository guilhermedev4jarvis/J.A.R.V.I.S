"""Action: context_triggers — fire routines/missions on system context events."""
from __future__ import annotations
from core.outcome import failed

def context_triggers(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._context_triggers_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("context_triggers", f"impl error: {e}")

TOOL = {
    "name": "context_triggers",
    "description": (
        "Gatilhos inteligentes por contexto: app_opened/closed, battery_below, "
        "idle_minutes, time_window. Dispara routine_orchestrator ou mission_planner "
        "automaticamente. Modes: add, remove, list, enable, disable, evaluate_now. "
        "Use for 'quando abrir o OBS ativa modo stream', 'se bateria abaixo de 20 avisa'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["add", "remove", "list", "enable", "disable", "evaluate_now"],
            },
            "name": {"type": "STRING"},
            "id": {"type": "STRING"},
            "condition_type": {
                "type": "STRING",
                "enum": ["app_opened", "app_closed", "battery_below", "idle_minutes", "time_window"],
            },
            "app": {"type": "STRING"},
            "percent": {"type": "NUMBER"},
            "minutes": {"type": "NUMBER"},
            "window": {"type": "STRING"},
            "fire_kind": {"type": "STRING", "description": "routine | mission | tool"},
            "fire_name": {"type": "STRING"},
            "battery": {"type": "NUMBER"},
            "idle_seconds": {"type": "NUMBER"},
            "dry_run": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": context_triggers,
    "tier": "core",
    "risk": "autonomous",
}
