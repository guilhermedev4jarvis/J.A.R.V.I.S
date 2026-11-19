"""Action: power_profile_manager — Windows power plans and brightness."""
from __future__ import annotations
from core.outcome import failed

def power_profile_manager(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._power_profile_manager_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("power_profile_manager", f"impl error: {e}")

TOOL = {
    "name": "power_profile_manager",
    "description": (
        "List/switch Windows power plans (powercfg) and set display brightness. "
        "Use for 'modo performance', 'economia de energia', 'brilho 50%', 'plano equilibrado'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["list", "set", "brightness", "performance", "saver", "balanced"],
            },
            "profile": {"type": "STRING"},
            "level": {"type": "NUMBER", "description": "Brightness 0-100"},
        },
        "required": [],
    },
    "handler": power_profile_manager,
    "tier": "core",
    "risk": "review",
}
