"""Modal overlays and side panels."""
from __future__ import annotations

def __getattr__(name: str):
    if name in {"SetupOverlay", "CustomizeOverlay", "PluginManagerOverlay", "UpdateReviewOverlay", "AudioDeviceOverlay", "MemoryOverlay", "ClipboardPanel", "PluginSettingsOverlay", "RemoteKeyOverlay", "_MinimalSettingsPanel", "BiometricsBootOverlay", "HueWheel"}:
        from ui import app as _app
        return getattr(_app, name)
    raise AttributeError(name)

__all__ = ["SetupOverlay", "CustomizeOverlay", "PluginManagerOverlay", "UpdateReviewOverlay", "AudioDeviceOverlay", "MemoryOverlay", "ClipboardPanel", "PluginSettingsOverlay", "RemoteKeyOverlay", "_MinimalSettingsPanel", "BiometricsBootOverlay", "HueWheel"]
