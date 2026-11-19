"""
hot_reload — reload actions and plugins without restarting JARVIS.

Uses importlib.reload on modules under actions/ and plugins/. Also refreshes
the in-process tool registry when core.action_loader / plugin_loader expose
a rediscover function.

Safe for development: does not touch the live Gemini session or audio pipeline.
"""
from __future__ import annotations
import ast

import importlib
import sys
from pathlib import Path
from typing import Any

from core.outcome import done, failed, ask

def _validate_syntax(path: Path) -> str | None:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        ast.parse(src)
        return None
    except SyntaxError as e:
        return str(e)

_BASE = Path(__file__).resolve().parents[2]
_ACTIONS_DIR = _BASE / "actions"
_PLUGINS_DIR = _BASE / "plugins"


def _module_name_from_path(path: Path, root: Path, prefix: str) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    return prefix + "." + ".".join(parts)


def _reload_module(modname: str) -> tuple[bool, str]:
    """Reload if already imported; otherwise import fresh.

    Failures are isolated: a broken module never aborts the rest of the batch,
    and a failed reload leaves the previous module object in sys.modules so the
    running session keeps the last-good code.
    """
    previous = sys.modules.get(modname)
    try:
        if previous is not None:
            importlib.reload(previous)
            return True, "reloaded"
        else:
            importlib.import_module(modname)
            return True, "imported"
    except Exception as e:
        # Restore last-good module object if reload corrupted sys.modules entry
        if previous is not None:
            sys.modules[modname] = previous
        return False, f"{type(e).__name__}: {e}"


def _list_py(dirpath: Path) -> list[Path]:
    if not dirpath.is_dir():
        return []
    return sorted(
        p for p in dirpath.rglob("*.py")
        if p.name != "__init__.py" and not p.name.startswith("_")
    )


def _rediscover_actions() -> str | None:
    """Try to refresh the live action registry if the loader supports it."""
    try:
        from core import action_loader
        if hasattr(action_loader, "discover_actions"):
            # Re-run discovery; exact side-effects depend on implementation
            action_loader.discover_actions()
            return "action_loader.discover_actions() called"
        if hasattr(action_loader, "reload_all"):
            action_loader.reload_all()
            return "action_loader.reload_all() called"
    except Exception as e:
        return f"action rediscover skipped: {e}"
    return "no rediscover hook found (modules still reloaded)"


def _rediscover_plugins() -> str | None:
    try:
        from core import plugin_loader
        if hasattr(plugin_loader, "discover_plugins"):
            plugin_loader.discover_plugins()
            return "plugin_loader.discover_plugins() called"
        if hasattr(plugin_loader, "reload_all"):
            plugin_loader.reload_all()
            return "plugin_loader.reload_all() called"
    except Exception as e:
        return f"plugin rediscover skipped: {e}"
    return "no rediscover hook found"


def hot_reload(parameters: dict | None = None, **_ctx) -> str:
    params = parameters or {}
    action = (params.get("action") or "actions").strip().lower()
    target = (params.get("name") or params.get("module") or "").strip()

    # ── reload one specific module ────────────────────────────────────────
    if action in ("one", "module", "single") or target:
        if not target:
            return ask("hot_reload", "which module?", hint="name=web_search or name=actions.web_search")

        # Normalise to full module path
        if not target.startswith("actions.") and not target.startswith("plugins."):
            # Prefer actions/
            if (_ACTIONS_DIR / f"{target}.py").exists():
                target = f"actions.{target}"
            elif (_PLUGINS_DIR / f"{target}.py").exists():
                target = f"plugins.{target}"
            else:
                return failed("hot_reload", f"could not find module for '{target}'")

        ok, msg = _reload_module(target)
        if not ok:
            return failed("hot_reload", msg, module=target)

        extra = ""
        if target.startswith("actions."):
            extra = _rediscover_actions() or ""
        elif target.startswith("plugins."):
            extra = _rediscover_plugins() or ""

        return done(
            "hot_reload",
            action="one",
            module=target,
            result=msg,
            registry=extra,
        )

    # ── reload all actions ────────────────────────────────────────────────
    if action in ("actions", "all_actions", "reload_actions"):
        files = _list_py(_ACTIONS_DIR)
        ok_list = []
        fail_list = []
        for path in files:
            try:
                rel = path.relative_to(_ACTIONS_DIR)
                modname = "actions." + ".".join(rel.with_suffix("").parts)
            except Exception:
                modname = f"actions.{path.stem}"
            success, msg = _reload_module(modname)
            if success:
                ok_list.append(path.stem)
            else:
                fail_list.append(f"{path.stem}: {msg}")

        reg = _rediscover_actions()
        return done(
            "hot_reload",
            action="actions",
            reloaded=len(ok_list),
            failed=len(fail_list),
            modules=", ".join(ok_list[:30]) + ("..." if len(ok_list) > 30 else ""),
            errors="; ".join(fail_list[:8]) if fail_list else "none",
            registry=reg,
        )

    # ── reload all plugins ────────────────────────────────────────────────
    if action in ("plugins", "all_plugins", "reload_plugins"):
        files = _list_py(_PLUGINS_DIR)
        ok_list = []
        fail_list = []
        for path in files:
            modname = f"plugins.{path.stem}"
            success, msg = _reload_module(modname)
            if success:
                ok_list.append(path.stem)
            else:
                fail_list.append(f"{path.stem}: {msg}")

        reg = _rediscover_plugins()
        return done(
            "hot_reload",
            action="plugins",
            reloaded=len(ok_list),
            failed=len(fail_list),
            modules=", ".join(ok_list) if ok_list else "(none)",
            errors="; ".join(fail_list[:8]) if fail_list else "none",
            registry=reg,
        )

    # ── everything ────────────────────────────────────────────────────────
    if action in ("all", "everything", "full"):
        # Actions first
        a_files = _list_py(_ACTIONS_DIR)
        p_files = _list_py(_PLUGINS_DIR)
        a_ok = a_fail = p_ok = p_fail = 0
        errors = []

        for path in a_files:
            try:
                rel = path.relative_to(_ACTIONS_DIR)
                _mn = "actions." + ".".join(rel.with_suffix("").parts)
            except Exception:
                _mn = f"actions.{path.stem}"
            ok, msg = _reload_module(_mn)
            if ok:
                a_ok += 1
            else:
                a_fail += 1
                errors.append(f"{_mn}: {msg}")

        for path in p_files:
            ok, msg = _reload_module(f"plugins.{path.stem}")
            if ok:
                p_ok += 1
            else:
                p_fail += 1
                errors.append(f"plugins.{path.stem}: {msg}")

        reg_a = _rediscover_actions()
        reg_p = _rediscover_plugins()

        return done(
            "hot_reload",
            action="all",
            actions_reloaded=a_ok,
            actions_failed=a_fail,
            plugins_reloaded=p_ok,
            plugins_failed=p_fail,
            errors="; ".join(errors[:10]) if errors else "none",
            registry_actions=reg_a,
            registry_plugins=reg_p,
        )

    # ── list currently imported ───────────────────────────────────────────
    if action in ("list", "imported"):
        imported_a = sorted(m for m in sys.modules if m.startswith("actions.") and m.count(".") == 1)
        imported_p = sorted(m for m in sys.modules if m.startswith("plugins.") and m.count(".") == 1)
        return done(
            "hot_reload",
            action="list",
            actions_imported=len(imported_a),
            plugins_imported=len(imported_p),
            actions=", ".join(m.split(".", 1)[1] for m in imported_a[:40]),
            plugins=", ".join(m.split(".", 1)[1] for m in imported_p[:20]),
        )

    return ask(
        "hot_reload",
        "what should I reload?",
        options="actions, plugins, all, one (name=...), list",
    )


TOOL = {
    "name": "hot_reload",
    "description": (
        "Reloads action and plugin modules in-process without restarting JARVIS. "
        "Useful while developing or after editing an action file. "
        "Actions: actions (reload all actions), plugins, all, "
        "one (name=module_stem or full dotted name), list (show imported modules). "
        "Also tries to refresh the tool registry via action_loader / plugin_loader."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "actions | plugins | all | one | list",
            },
            "name": {
                "type": "STRING",
                "description": "Module name for action=one (e.g. web_search or actions.web_search)",
            },
        },
        "required": [],
    },
    "handler": hot_reload,
    "tier": "core",
}
