"""Unified programming studio → core.code_engine + legacy code_* modes."""
from __future__ import annotations

from core.code_engine import get_engine
from core.outcome import done, failed, ask


def _dispatch(impl: str, names: list[str], params: dict, **ctx) -> str:
    import importlib
    mod = importlib.import_module(f"actions.ai_core.{impl}")
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
    return failed("code_studio", f"missing {impl}")


def code_studio(parameters=None, **ctx) -> str:
    params = dict(parameters or {})
    mode = str(params.get("mode") or params.get("action") or "pipeline").strip().lower()
    goal = str(params.get("goal") or params.get("prompt") or params.get("description") or "").strip()
    engine = get_engine()

    if mode in ("help", "status"):
        return done("code_studio", modes=["pipeline", "forge", "helper", "review", "dev", "self", "programador"])

    if mode in ("pipeline", "assist", "code_assist", "implement"):
        if not goal:
            return ask("code_studio", "goal?")
        return engine.pipeline(goal, write=True, run=False).as_outcome("code_studio")

    if mode in ("forge", "code_forge", "generate"):
        if not goal:
            return ask("code_studio", "prompt?")
        return engine.forge(goal, run=str(params.get("run") or "true").lower() in ("1", "true", "yes", "")).as_outcome("code_studio")

    if mode in ("helper", "code_helper", "write", "edit"):
        return _dispatch("_code_helper_impl", ["code_helper"], params, **ctx)

    if mode in ("review", "code_review_local", "analyze"):
        return _dispatch("_code_review_local_impl", ["code_review_local"], params, **ctx)

    if mode in ("dev", "dev_agent"):
        return _dispatch("_dev_agent_impl", ["dev_agent"], params, **ctx)

    if mode in ("self", "self_program"):
        return _dispatch("_self_program_impl", ["self_program"], params, **ctx)

    if mode in ("programador", "program"):
        return _dispatch("_programador_impl", ["programador"], params, **ctx)

    if goal:
        return engine.pipeline(goal, write=True, run=False).as_outcome("code_studio")
    return ask("code_studio", "mode or goal?", hint="pipeline|forge|helper|review|dev|self")


TOOL = {
    "name": "code_studio",
    "description": "Studio de programacao unificado (CodeEngine): mode=pipeline|forge|helper|review|dev|self|programador.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {"type": "STRING"},
            "action": {"type": "STRING"},
            "goal": {"type": "STRING"},
            "prompt": {"type": "STRING"},
            "path": {"type": "STRING"},
            "run": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": code_studio,
    "tier": "core",
    "risk": "review",
}
