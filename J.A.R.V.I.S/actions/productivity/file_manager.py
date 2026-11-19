"""Unified file manager (controller/processor/organize)."""
from __future__ import annotations

from core.outcome import done, failed, ask


def _dispatch(impl: str, names: list[str], params: dict, **ctx) -> str:
    import importlib
    mod = importlib.import_module(f"actions.productivity.{impl}")
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
    return failed("file_manager", f"missing {impl}")


def file_manager(parameters=None, **ctx) -> str:
    params = dict(parameters or {})
    mode = str(params.get("mode") or params.get("action") or "control").strip().lower()
    if mode in ("control", "file_controller", "delete", "move", "copy", "rename"):
        return _dispatch("_file_controller_impl", ["file_controller", "run"], params, **ctx)
    if mode in ("process", "file_processor", "read", "pdf", "docx"):
        return _dispatch("_file_processor_impl", ["file_processor", "run"], params, **ctx)
    if mode in ("organize", "file_organize", "sort"):
        return _dispatch("_file_organize_impl", ["file_organize", "run"], params, **ctx)
    if mode == "help":
        return done("file_manager", modes=["control", "process", "organize"])
    return _dispatch("_file_controller_impl", ["file_controller", "run"], params, **ctx)


TOOL = {
    "name": "file_manager",
    "description": "Arquivos unificados: mode=control|process|organize.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {"type": "STRING"},
            "action": {"type": "STRING"},
            "path": {"type": "STRING"},
            "dest": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": file_manager,
    "tier": "core",
    "risk": "destructive",
}
