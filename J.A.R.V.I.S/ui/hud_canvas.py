"""HUD canvas and hologram geometry."""
from __future__ import annotations

def __getattr__(name: str):
    if name in {"HudCanvas", "_particle_sphere_points", "_globe_static_geometry", "_sphere_xyz"}:
        from ui import app as _app
        return getattr(_app, name)
    raise AttributeError(name)

__all__ = ["HudCanvas", "_particle_sphere_points", "_globe_static_geometry", "_sphere_xyz"]
