"""Unified desktop/window/computer/agent control."""
from __future__ import annotations

from core.outcome import done, failed, ask


def _dispatch(impl: str, names: list[str], params: dict, **ctx) -> str:
    import importlib
    mod = importlib.import_module(f"actions.desktop.{impl}")
    for fn in names:
        h = getattr(mod, fn, None)
        if callable(h):
            try:
                return h(params, **ctx)
            except TypeError:
                try:
                    return h(parameters=params)
                except TypeError:
                    return h(params)
    return failed("desktop_control", f"missing {impl}")


def desktop_control(parameters=None, **ctx) -> str:
    params = dict(parameters or {})
    mode = str(params.get("mode") or params.get("action") or "desktop").strip().lower()
    if mode in ("desktop", "desktop_control", "click", "type", "hotkey"):
        return _dispatch("_desktop_impl", ["desktop_control", "desktop", "run"], params, **ctx)
    if mode in ("window", "window_manager"):
        return _dispatch("_window_manager_impl", ["window_manager", "run"], params, **ctx)
    if mode in ("computer", "computer_control", "settings"):
        return _dispatch("_computer_control_impl", ["computer_control", "run"], params, **ctx)
    if mode in ("agent", "desktop_agent", "autonomous"):
        return _dispatch("_desktop_agent_impl", ["desktop_agent", "run"], params, **ctx)
    if mode == "help":
        return done("desktop_control", modes=["desktop", "window", "computer", "agent"])
    return _dispatch("_desktop_impl", ["desktop_control", "desktop", "run"], params, **ctx)


TOOL = {
    "name": "desktop_control",
    "description": "Desktop unificado: mode=desktop|window|computer|agent.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {"type": "STRING"},
            "action": {"type": "STRING"},
            "query": {"type": "STRING"},
            "text": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": desktop_control,
    "tier": "core",
    "risk": "autonomous",
}
