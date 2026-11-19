"""Shared constants and process-wide state for the J.A.R.V.I.S. runtime."""
from __future__ import annotations

import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# Project root: package lives at <root>/main/*.py → parents[1]
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]


def get_base_dir() -> Path:
    """Install root (frozen exe dir or repository root)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return PROJECT_ROOT


BASE_DIR: Path = get_base_dir()
API_CONFIG_PATH: Path = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH: Path = BASE_DIR / "core" / "prompt.txt"

WAKE_SLEEP_TIMEOUT: float = 120.0
LIVE_MODEL: str = "models/gemini-3.8-live"
CHANNELS: int = 1
SEND_SAMPLE_RATE: int = 16000
RECEIVE_SAMPLE_RATE: int = 24000
CHUNK_SIZE: int = 1024
_LEVEL_FLOOR: float = 60.0
_LEVEL_FULL: float = 2600.0

# Cross-thread coordination
AUDIO_LOCK = threading.RLock()
SESSION_LOCK = threading.RLock()
SHUTDOWN_EVENT = threading.Event()


@dataclass
class SessionContext:
    """Lightweight session bag (avoid circular imports with UI/orchestrator)."""
    speaking: bool = False
    push_to_talk: bool = False
    awake: bool = True
    meta: dict[str, Any] = field(default_factory=dict)


SESSION = SessionContext()

__all__ = [
    "PROJECT_ROOT",
    "get_base_dir",
    "BASE_DIR",
    "API_CONFIG_PATH",
    "PROMPT_PATH",
    "WAKE_SLEEP_TIMEOUT",
    "LIVE_MODEL",
    "CHANNELS",
    "SEND_SAMPLE_RATE",
    "RECEIVE_SAMPLE_RATE",
    "CHUNK_SIZE",
    "_LEVEL_FLOOR",
    "_LEVEL_FULL",
    "AUDIO_LOCK",
    "SESSION_LOCK",
    "SHUTDOWN_EVENT",
    "SessionContext",
    "SESSION",
]
