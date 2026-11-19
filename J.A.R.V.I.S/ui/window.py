"""Main window shell and JarvisUI facade class."""
from __future__ import annotations

def __getattr__(name: str):
    if name in {"MainWindow", "_RootShim", "JarvisUI"}:
        from ui import app as _app
        return getattr(_app, name)
    raise AttributeError(name)

__all__ = ["MainWindow", "_RootShim", "JarvisUI"]
