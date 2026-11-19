"""Action: intruder_alert — absence guardian with face check, lock and audit."""
from __future__ import annotations
from core.outcome import failed

def intruder_alert(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._intruder_alert_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("intruder_alert", f"impl error: {e}")

TOOL = {
    "name": "intruder_alert",
    "description": (
        "Arm an absence guardian: periodically checks the webcam via face_auth; "
        "if a non-owner face is detected, locks the workstation, saves a photo under "
        "memory/audit/ and logs via audit. Use for 'ativa modo guardião', "
        "'protege o PC enquanto eu saio', 'desarma o intruder alert'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["start", "stop", "status", "test_lock"]},
            "poll_seconds": {"type": "NUMBER", "description": "Seconds between checks (default 8)"},
        },
        "required": [],
    },
    "handler": intruder_alert,
    "tier": "core",
    "risk": "destructive",
}
