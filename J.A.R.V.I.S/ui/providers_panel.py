"""Providers configuration overlay."""
from __future__ import annotations

def __getattr__(name: str):
    if name in {"ProvidersOverlay"}:
        from ui import app as _app
        return getattr(_app, name)
    raise AttributeError(name)

__all__ = ["ProvidersOverlay"]
