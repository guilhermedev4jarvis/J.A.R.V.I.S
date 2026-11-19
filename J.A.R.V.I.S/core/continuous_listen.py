"""Copiloto de voz contínuo — follow-up sem wake-word após TTS."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable, Optional

_BASE = Path(__file__).resolve().parents[1]
_CFG = _BASE / "config" / "audio_latency.json"

_state = {
    "mode": "idle",  # idle | listening_wake | listening_followup | speaking
    "followup_until": 0.0,
    "lock": threading.Lock(),
}


def _window_sec() -> float:
    try:
        data = json.loads(_CFG.read_text(encoding="utf-8"))
        return float(data.get("continuous_listen_window_sec") or 18)
    except Exception:
        return 18.0


def _end_phrases() -> list[str]:
    try:
        data = json.loads(_CFG.read_text(encoding="utf-8"))
        return list(data.get("end_phrases") or [])
    except Exception:
        return ["obrigado", "só isso"]


def get_listen_state() -> str:
    with _state["lock"]:
        mode = _state["mode"]
        if mode == "listening_followup" and time.time() > float(_state["followup_until"]):
            _state["mode"] = "listening_wake"
            return "listening_wake"
        return mode


def set_speaking(active: bool = True) -> None:
    with _state["lock"]:
        _state["mode"] = "speaking" if active else "listening_followup"
        if not active:
            _state["followup_until"] = time.time() + _window_sec()


def open_followup_window(seconds: Optional[float] = None) -> float:
    sec = float(seconds if seconds is not None else _window_sec())
    with _state["lock"]:
        _state["mode"] = "listening_followup"
        _state["followup_until"] = time.time() + sec
    return sec


def close_followup(to_wake: bool = True) -> None:
    with _state["lock"]:
        _state["mode"] = "listening_wake" if to_wake else "idle"
        _state["followup_until"] = 0.0


def should_accept_without_wake(transcript: str = "") -> bool:
    """True if inside follow-up window and phrase is not an end marker."""
    low = (transcript or "").lower().strip()
    with _state["lock"]:
        if _state["mode"] != "listening_followup":
            return False
        if time.time() > float(_state["followup_until"]):
            _state["mode"] = "listening_wake"
            return False
    for p in _end_phrases():
        if p in low:
            close_followup(True)
            return False
    return True


def on_tts_finished() -> None:
    """Call after Jarvis finishes speaking to open follow-up window."""
    open_followup_window()
