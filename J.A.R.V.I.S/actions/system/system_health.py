"""Canonical system health / status monitor (wraps private _system_monitor_impl)."""
from __future__ import annotations

from core.outcome import done, failed

from ._system_monitor_impl import SystemMonitor, get_system_status  # noqa: F401


def _dispatch(impl: str, fn_candidates: list[str], params: dict, **ctx) -> str:
    import importlib
    mod = importlib.import_module(f"actions.system.{impl}")
    for fn in fn_candidates:
        h = getattr(mod, fn, None)
        if callable(h):
            try:
                return h(params, **ctx)
            except TypeError:
                try:
                    return h(parameters=params, **ctx)
                except TypeError:
                    try:
                        return h(params)
                    except TypeError:
                        return h()
    return failed("system_health", f"no handler in {impl}")


def system_health(parameters=None, **ctx) -> str:
    params = dict(parameters or {})
    mode = str(params.get("mode") or params.get("action") or "health").strip().lower()
    if mode in ("status", "health", "system_health", "info"):
        return _dispatch("_system_monitor_impl", ["system_health", "system_monitor", "run", "get_status"], params, **ctx)
    if mode in ("hardware_sensors", "sensors", "hw"):
        return _dispatch("_system_monitor_impl", ["system_monitor", "run"], {**params, "mode": "hardware_sensors"}, **ctx)
    if mode in ("resources", "system_resources"):
        try:
            return _dispatch("_system_resources_monitor_impl", ["system_resources_monitor", "run"], params, **ctx)
        except Exception:
            return _dispatch("_system_monitor_impl", ["system_monitor", "run"], {**params, "mode": "resources"}, **ctx)
    if mode in ("watch", "background"):
        return _dispatch("_background_monitor_impl", ["check_all", "run"], params, **ctx)
    return _dispatch("_system_monitor_impl", ["system_monitor", "run", "system_health"], params, **ctx)


TOOL = {
    "name": "system_health",
    "description": "Saude geral do host (CPU/RAM/disco). USE para diagnostico rapido. NAO USE para monitor detalhado em loop (system_resources_monitor).",
    
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {"type": "STRING"},
            "action": {"type": "STRING"},
            "query": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": system_health,
    "tier": "core",
    "risk": "safe",
}
