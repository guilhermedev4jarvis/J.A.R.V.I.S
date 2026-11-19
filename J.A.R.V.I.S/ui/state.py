"""Thread-safe UI state and marshaling onto the Qt main thread."""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

_ui_queue: queue.Queue = queue.Queue()
_lock = threading.RLock()


@dataclass
class UiState:
    speaking: bool = False
    audio_level: float = 0.0
    status: str = "idle"
    biometrics_phase: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


STATE = UiState()


def post(fn: Callable[[], Any]) -> None:
    """Schedule callable to run on the UI thread (drained by JarvisUI/MainWindow)."""
    _ui_queue.put(fn)


def drain(max_items: int = 64) -> int:
    """Execute pending UI callbacks; return number processed."""
    n = 0
    while n < max_items:
        try:
            fn = _ui_queue.get_nowait()
        except queue.Empty:
            break
        try:
            fn()
        except Exception:
            pass
        n += 1
    return n


def set_status(status: str) -> None:
    with _lock:
        STATE.status = status


def set_audio_level(level: float) -> None:
    with _lock:
        STATE.audio_level = float(level)


__all__ = ["STATE", "UiState", "post", "drain", "set_status", "set_audio_level", "_ui_queue"]
