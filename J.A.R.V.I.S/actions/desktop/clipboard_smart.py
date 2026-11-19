"""Unified clipboard (smart + basic get/set) — canonical tool name: clipboard_smart."""
from __future__ import annotations

from core.outcome import failed


def _dispatch(impl: str, names: list[str], params: dict, **ctx) -> str:
    import importlib
    # domain-local private module
    mod = importlib.import_module(f"actions.desktop.{impl}" if not impl.startswith("actions.") else impl)
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
    return failed("clipboard_smart", f"missing {impl}")


def clipboard_smart(parameters=None, **ctx) -> str:
    params = dict(parameters or {})
    mode = str(params.get("mode") or params.get("action") or "smart").strip().lower()
    if mode in ("basic", "get", "set", "clear"):
        return _dispatch("_clipboard_smart_impl", ["clipboard_smart", "run", "clipboard"], params, **ctx)
    return _dispatch("_clipboard_smart_impl", ["clipboard_smart", "run"], params, **ctx)


TOOL = {
    "name": "clipboard_smart",
    "description": (
        "Clipboard unificado: ler, escrever, organizar e historico da area de transferencia. "
        "mode=smart|get|set|clear."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {"type": "STRING"},
            "action": {"type": "STRING"},
            "text": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": clipboard_smart,
    "tier": "core",
    "risk": "review",
}
