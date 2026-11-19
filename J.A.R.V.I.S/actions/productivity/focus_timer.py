"""
focus_timer — Pomodoro / deep-work sessions with optional site blocking hints.

State is kept in a small JSON file under config/. Blocking is advisory on
non-Windows platforms; on Windows it can append hosts-file entries when the
user confirms elevated permission (we never silently elevate).
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from core.outcome import done, failed, ask

_BASE = Path(__file__).resolve().parents[2]
_STATE_PATH = _BASE / "config" / "focus_timer.json"
_lock = threading.Lock()

_DEFAULT_DISTRACTIONS = [
    "www.youtube.com",
    "youtube.com",
    "www.twitter.com",
    "twitter.com",
    "x.com",
    "www.reddit.com",
    "reddit.com",
    "www.instagram.com",
    "instagram.com",
    "www.facebook.com",
    "facebook.com",
    "www.tiktok.com",
    "tiktok.com",
    "www.netflix.com",
    "netflix.com",
]


def _load() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def focus_timer(parameters=None, **_ctx) -> str:
    params = parameters or {}
    action = (params.get("action") or "status").strip().lower()
    minutes = int(params.get("minutes") or 25)
    minutes = max(1, min(minutes, 180))
    label = (params.get("label") or params.get("task") or "focus").strip()

    with _lock:
        state = _load()

        if action in ("start", "begin", "pomodoro"):
            if state.get("active"):
                ends = state.get("ends_at", "")
                return failed(
                    "focus_timer",
                    f"a session is already running until {ends}",
                    label=state.get("label"),
                )
            now = datetime.now()
            ends = now + timedelta(minutes=minutes)
            state = {
                "active": True,
                "label": label,
                "minutes": minutes,
                "started_at": now.isoformat(timespec="seconds"),
                "ends_at": ends.isoformat(timespec="seconds"),
                "block_sites": bool(params.get("block_sites", False)),
            }
            _save(state)
            note = ""
            if state["block_sites"]:
                note = (
                    " Site blocking was requested — this tool records the intent; "
                    "actual hosts-file edits require admin rights and are not "
                    "applied automatically. Use a dedicated blocker if needed."
                )
            return done(
                "focus_timer",
                action="start",
                label=label,
                minutes=minutes,
                ends_at=state["ends_at"],
                note=note.strip(),
            )

        if action in ("stop", "cancel", "end"):
            if not state.get("active"):
                return done("focus_timer", action="stop", note="no active session")
            state["active"] = False
            state["stopped_at"] = datetime.now().isoformat(timespec="seconds")
            _save(state)
            return done("focus_timer", action="stop", label=state.get("label", ""))

        if action in ("status", "check"):
            if not state.get("active"):
                return done("focus_timer", action="status", active=False, note="no active session")
            try:
                ends = datetime.fromisoformat(state["ends_at"])
                remaining = max(0, int((ends - datetime.now()).total_seconds()))
            except Exception:
                remaining = 0
            if remaining <= 0:
                state["active"] = False
                state["completed_at"] = datetime.now().isoformat(timespec="seconds")
                _save(state)
                return done(
                    "focus_timer",
                    action="status",
                    active=False,
                    completed=True,
                    label=state.get("label", ""),
                    note="session finished",
                )
            return done(
                "focus_timer",
                action="status",
                active=True,
                label=state.get("label", ""),
                remaining_seconds=remaining,
                remaining_minutes=round(remaining / 60, 1),
                ends_at=state.get("ends_at"),
            )

        if action in ("extend",):
            if not state.get("active"):
                return failed("focus_timer", "no active session to extend")
            try:
                ends = datetime.fromisoformat(state["ends_at"])
            except Exception:
                ends = datetime.now()
            ends = ends + timedelta(minutes=minutes)
            state["ends_at"] = ends.isoformat(timespec="seconds")
            _save(state)
            return done(
                "focus_timer",
                action="extend",
                added_minutes=minutes,
                ends_at=state["ends_at"],
            )

    return failed(
        "focus_timer",
        f"unknown action '{action}'",
        allowed="start, stop, status, extend",
    )


TOOL = {  # also covers generic countdown requests formerly served by timer.py

    "name": "focus_timer",
    "description": (
        "Starts or manages a focus / Pomodoro timer. "
        "Actions: start (default 25 min), stop, status, extend. "
        "Optional block_sites=true records intent to avoid distractions "
        "(does not silently edit the hosts file). "
        "Use when the user wants to concentrate, start a pomodoro, or check "
        "how much time is left in the current focus session."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "start | stop | status | extend",
            },
            "minutes": {
                "type": "NUMBER",
                "description": "Duration in minutes (default 25, max 180).",
            },
            "label": {
                "type": "STRING",
                "description": "What you are focusing on.",
            },
            "task": {"type": "STRING", "description": "Alias for label."},
            "block_sites": {
                "type": "BOOLEAN",
                "description": "Record intent to block common distraction sites.",
            },
        },
        "required": ["action"],
    },
    "handler": focus_timer,
    "tier": "core",
}
