"""Action: radar_climatico_rp."""
from __future__ import annotations
from core.outcome import failed

def radar_climatico_rp(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._radar_climatico_rp_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("radar_climatico_rp", f"impl error: {e}")

TOOL = {
    "name": "radar_climatico_rp",
    "description": ("Radar climático de São José do Rio Preto (-20.8113,-49.3758) via Open-Meteo. "
    "Gatilhos: ativar radar climático, vai chover forte hoje? Thread a cada 45 min."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["start", "stop", "status", "check_now"]},
            "text": {"type": "STRING"},
            "name": {"type": "STRING"},
            "plate": {"type": "STRING"},
            "query": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": radar_climatico_rp,
    "tier": "core",
    "risk": "safe",
}
