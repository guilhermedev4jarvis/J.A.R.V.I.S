"""Command orchestration and live session (JarvisLive)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

def __getattr__(name: str):
    # Lazy to keep ``import main`` free of heavy side effects until needed
    if name in {"JarvisLive", "_ReconnectSignal", "_is_reconnect_signal", "_keep_context_of"}:
        import importlib; _app = importlib.import_module("main.app")
        return getattr(_app, name)
    raise AttributeError(name)

__all__ = ["JarvisLive", "_ReconnectSignal", "_is_reconnect_signal", "_keep_context_of"]
