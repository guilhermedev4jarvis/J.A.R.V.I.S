"""Wake word module RETIRED.

J.A.R.V.I.S. now uses continuous listening (VAD / always-on mic path).
This stub keeps legacy imports from ui.py / main.py from crashing the boot
without loading openwakeword, onnxruntime or porcupine.
"""
from __future__ import annotations

from typing import Callable, Optional


def is_ready() -> bool:
    """Always False — feature removed."""
    return False


def install_and_download() -> tuple[bool, str]:
    return False, "Wake word removida — o assistente escuta continuamente (VAD)."


class WakeWordDetector:
    """No-op detector kept for API compatibility with older UI hooks."""

    def __init__(self, on_detect: Optional[Callable[[], None]] = None, **_kwargs):
        self.on_detect = on_detect
        self.ready = False
        self._running = False

    def start(self) -> bool:
        self.ready = False
        self._running = False
        return False

    def stop(self) -> None:
        self._running = False

    def close(self) -> None:
        self.stop()


def wake_or_followup_required(transcript: str = "") -> bool:
    """Return False if follow-up window allows speech without wake word."""
    try:
        from core.continuous_listen import should_accept_without_wake
        if should_accept_without_wake(transcript):
            return False
    except Exception:
        pass
    return True
