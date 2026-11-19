"""Canonical per-resource monitor (CPU/RAM/disk detail)."""
from __future__ import annotations

from core.outcome import failed


def system_resources_monitor(parameters=None, **ctx) -> str:
    params = dict(parameters or {})
    params.setdefault("mode", "resources")
    try:
        from ._system_resources_monitor_impl import run
        return run(params, **ctx)
    except Exception:
        try:
            import actions.system._system_monitor_impl as impl
            for fn in ("run", "system_monitor", "system_resources_monitor"):
                h = getattr(impl, fn, None)
                if callable(h):
                    try:
                        return h(params, **ctx)
                    except TypeError:
                        return h(params)
            return failed("system_resources_monitor", "no handler")
        except Exception as e:
            return failed("system_resources_monitor", str(e))


TOOL = {
    "name": "system_resources_monitor",
    "description": "Detalhe de recursos do sistema (CPU, RAM, disco, rede).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {"type": "STRING"},
            "action": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": system_resources_monitor,
    "tier": "core",
    "risk": "safe",
}
