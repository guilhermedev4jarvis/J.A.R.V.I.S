"""Action: meeting_transcriber — record/transcribe meetings and save action notes."""
from __future__ import annotations
from core.outcome import failed

def meeting_transcriber(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._meeting_transcriber_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("meeting_transcriber", f"impl error: {e}")

TOOL = {
    "name": "meeting_transcriber",
    "description": (
        "Record meeting audio from the default mic, transcribe with Whisper when "
        "available, and save a structured summary with action items via quick_note. "
        "Use for 'grava a reunião', 'transcreve a meeting', 'resume a reunião'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["record", "status", "transcribe_file"]},
            "seconds": {"type": "NUMBER", "description": "Capture length 5-600s (default 30)"},
            "title": {"type": "STRING"},
            "path": {"type": "STRING", "description": "Existing audio file for transcribe_file"},
        },
        "required": [],
    },
    "handler": meeting_transcriber,
    "tier": "core",
    "risk": "review",
}
