"""Reusable UI widgets."""
from __future__ import annotations

def __getattr__(name: str):
    if name in {"MetricBar", "LogWidget", "FileDropZone", "_DropCanvas", "ConfirmBanner", "_HudOverlay", "_ScrollSafeCombo", "_SysMetrics", "_file_category", "_fmt_size"}:
        from ui import app as _app
        return getattr(_app, name)
    raise AttributeError(name)

__all__ = ["MetricBar", "LogWidget", "FileDropZone", "_DropCanvas", "ConfirmBanner", "_HudOverlay", "_ScrollSafeCombo", "_SysMetrics", "_file_category", "_fmt_size"]
