"""Heavy logic for routine_orchestrator — macros of sequential tool calls."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Optional

from core.outcome import ask, done, failed, started, unverified

_BASE = Path(__file__).resolve().parents[2]
_ROUTINES = _BASE / "config" / "routines.json"
_lock = threading.Lock()


def _load() -> dict:
    if not _ROUTINES.is_file():
        return {"version": 1, "routines": {}}
    try:
        return json.loads(_ROUTINES.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "routines": {}}


def _save(data: dict) -> None:
    _ROUTINES.parent.mkdir(parents=True, exist_ok=True)
    _ROUTINES.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _speak(text: str, player=None) -> None:
    if player:
        try:
            say = getattr(player, "plugin_say", None) or getattr(player, "say", None) or getattr(player, "request_say", None)
            if callable(say):
                say(text)
                return
        except Exception:
            pass
    try:
        from core import tts as tts_mod
        player_tts = tts_mod.create_tts_player({})
        player_tts.speak(text)
    except Exception:
        print(f"[routine] TTS: {text}")


def _run_tool(tool_name: str, params: dict, player=None) -> str:
    """Best-effort invoke of another action by TOOL name."""
    try:
        from core import action_loader
        tools = getattr(action_loader, "TOOLS", None) or getattr(action_loader, "get_tools", lambda: {})()
        if callable(tools):
            tools = tools()
        entry = None
        if isinstance(tools, dict):
            entry = tools.get(tool_name)
        if entry is None:
            # direct import fallback
            mod = __import__(f"actions.{tool_name}", fromlist=["TOOL"])
            entry = getattr(mod, "TOOL", None)
        if not entry:
            return failed("routine_orchestrator", f"tool not found: {tool_name}")
        handler = entry.get("handler") if isinstance(entry, dict) else None
        if not callable(handler):
            return failed("routine_orchestrator", f"handler missing for {tool_name}")
        try:
            return handler(parameters=params, player=player)
        except TypeError:
            return handler(params)
    except Exception as e:
        return failed("routine_orchestrator", f"step {tool_name} failed: {e}")


def run(parameters: Optional[dict] = None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or p.get("mode") or "list").strip().lower()
    name = str(p.get("name") or p.get("routine") or "").strip()
    data = _load()
    routines = data.setdefault("routines", {})

    if action in ("list", "show"):
        names = sorted(routines.keys())
        return done("routine_orchestrator", op="list", count=len(names), routines=",".join(names) or "(none)")

    if action in ("get", "describe"):
        if not name or name not in routines:
            return ask("routine_orchestrator", "Qual rotina? " + (", ".join(routines) or "nenhuma cadastrada"))
        r = routines[name]
        return done("routine_orchestrator", op="get", name=name, steps=len(r.get("steps") or []), description=r.get("description") or "")

    if action in ("create", "add", "save"):
        if not name:
            return ask("routine_orchestrator", "Qual o nome da rotina a criar?")
        steps = p.get("steps")
        if isinstance(steps, str):
            try:
                steps = json.loads(steps)
            except Exception:
                steps = []
        if not isinstance(steps, list) or not steps:
            return failed("routine_orchestrator", "steps must be a non-empty JSON list of {tool, params, speak?}")
        routines[name] = {
            "description": str(p.get("description") or ""),
            "steps": steps,
        }
        with _lock:
            _save(data)
        return done("routine_orchestrator", op="create", name=name, steps=len(steps))

    if action in ("delete", "remove"):
        if not name or name not in routines:
            return failed("routine_orchestrator", f"rotina inexistente: {name or '(vazio)'}")
        del routines[name]
        with _lock:
            _save(data)
        return done("routine_orchestrator", op="delete", name=name)

    if action in ("run", "execute", "start"):
        if not name or name not in routines:
            return ask("routine_orchestrator", "Qual rotina executar? " + (", ".join(routines) or "nenhuma"))
        routine = routines[name]
        steps = list(routine.get("steps") or [])
        if not steps:
            return failed("routine_orchestrator", f"rotina '{name}' sem passos")

        def _bg():
            results = []
            for i, step in enumerate(steps, 1):
                tool = str(step.get("tool") or "").strip()
                params = step.get("params") or {}
                speak = str(step.get("speak") or f"Etapa {i}: {tool}").strip()
                _speak(speak, player)
                if not tool:
                    results.append(f"{i}:missing_tool")
                    continue
                out = _run_tool(tool, params if isinstance(params, dict) else {}, player=player)
                results.append(f"{i}:{tool}:{(out or '')[:80]}")
                time.sleep(0.4)
            print(f"[routine] done {name}: {results}")

        threading.Thread(target=_bg, daemon=True, name=f"routine-{name[:20]}").start()
        return started("routine_orchestrator", op="run", name=name, steps=len(steps))

    return failed("routine_orchestrator", f"action desconhecida: {action}. Use list|get|create|delete|run")
