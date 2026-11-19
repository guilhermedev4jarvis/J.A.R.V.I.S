"""J.A.R.V.I.S. UI package (PyQt6). Compatible with ``from ui import JarvisUI``."""
from __future__ import annotations

from ui.theme import (
    APP_NAME,
    APP_VERSION,
    APP_AUTHOR,
    BASE_DIR,
    CONFIG_DIR,
    _base_dir,
)

__all__ = [
    "JarvisUI",
    "MainWindow",
    "HudCanvas",
    "APP_NAME",
    "APP_VERSION",
    "APP_AUTHOR",
    "BASE_DIR",
    "CONFIG_DIR",
    "_base_dir",
    "C",
    "apply_ui_accent",
    "current_palette",
    "qcol",
]


def __getattr__(name: str):
    if name in {"JarvisUI", "MainWindow", "HudCanvas", "C", "apply_ui_accent",
                "current_palette", "qcol", "retheme_all_widgets", "BiometricsBootOverlay",
                "ConfirmBanner", "LogWidget", "MetricBar"}:
        from ui import app as _app
        return getattr(_app, name)
    raise AttributeError(f"module 'ui' has no attribute {name!r}")
