"""J.A.R.V.I.S. — package entry facade (compatible with legacy ``import main``).

Heavy runtime (Gemini, sounddevice, UI) loads only when symbols like
``JarvisLive`` or ``main`` are accessed.
"""
from __future__ import annotations

import importlib
from typing import Any

from main import bootstrap as _bootstrap  # noqa: F401
from main.state import (
    PROJECT_ROOT,
    BASE_DIR,
    get_base_dir,
    SEND_SAMPLE_RATE,
    RECEIVE_SAMPLE_RATE,
    LIVE_MODEL,
    SHUTDOWN_EVENT,
)

__all__ = [
    "PROJECT_ROOT",
    "BASE_DIR",
    "get_base_dir",
    "SEND_SAMPLE_RATE",
    "RECEIVE_SAMPLE_RATE",
    "LIVE_MODEL",
    "SHUTDOWN_EVENT",
    "JarvisLive",
    "main",
    "_ensure_audiorelay_running",
    "app",
]


def _load_app():
    """Load main.app without going through this package's __getattr__ (avoids recursion)."""
    return importlib.import_module("main.app")


def __getattr__(name: str) -> Any:
    if name == "app":
        return _load_app()
    if name == "JarvisLive":
        return getattr(_load_app(), "JarvisLive")
    if name == "main":
        from main.lifecycle import main as _main
        return _main
    if name == "_ensure_audiorelay_running":
        from main.lifecycle import _ensure_audiorelay_running as _ar
        return _ar
    # fallback: attributes defined on app module
    try:
        return getattr(_load_app(), name)
    except AttributeError as e:
        raise AttributeError(f"module 'main' has no attribute {name!r}") from e
