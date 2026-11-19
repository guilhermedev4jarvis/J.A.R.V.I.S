"""Unified network status + guard."""
from __future__ import annotations

from core.outcome import done, failed, ask


def _dispatch(impl: str, names: list[str], params: dict, **ctx) -> str:
    import importlib
    mod = importlib.import_module(f"actions.system.{impl}")
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
    return failed("network_manager", f"missing {impl}")


def network_manager(parameters=None, **ctx) -> str:
    params = dict(parameters or {})
    mode = str(params.get("mode") or params.get("action") or "status").strip().lower()
    if mode in ("status", "network_status", "info"):
        return _dispatch("_network_status_impl", ["network_status", "run"], params, **ctx)
    if mode in ("guard", "network_guard", "block", "allow"):
        return _dispatch("_network_guard_impl", ["network_guard", "run"], params, **ctx)
    if mode == "help":
        return done("network_manager", modes=["status", "guard"])
    return _dispatch("_network_status_impl", ["network_status", "run"], params, **ctx)


TOOL = {
    "name": "network_manager",
    "description": "Rede unificada: mode=status|guard.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {"type": "STRING"},
            "action": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": network_manager,
    "tier": "core",
    "risk": "review",
}
