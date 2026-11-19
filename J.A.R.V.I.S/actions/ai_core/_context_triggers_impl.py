"""context_triggers — event/context rules that fire routines or missions."""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from core.outcome import ask, done, failed, started

_BASE = Path(__file__).resolve().parents[2]
_CFG = _BASE / "config" / "context_triggers.json"
_lock = threading.Lock()


def _load() -> dict:
    if not _CFG.is_file():
        return {"version": 1, "enabled": True, "rules": []}
    try:
        return json.loads(_CFG.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "enabled": True, "rules": []}


def _save(data: dict) -> None:
    _CFG.parent.mkdir(parents=True, exist_ok=True)
    _CFG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _battery_percent() -> Optional[float]:
    try:
        import psutil
        bat = psutil.sensors_battery()
        if bat is not None:
            return float(bat.percent)
    except Exception:
        pass
    return None


def _idle_seconds() -> Optional[float]:
    # Best-effort; platforms vary. Return None if unknown.
    try:
        import ctypes
        import platform
        if platform.system() == "Windows":
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            li = LASTINPUTINFO()
            li.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li)):
                millis = ctypes.windll.kernel32.GetTickCount() - li.dwTime
                return millis / 1000.0
    except Exception:
        pass
    return None


def _process_names() -> set[str]:
    names = set()
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            n = (p.info.get("name") or "").strip()
            if n:
                names.add(n.lower())
    except Exception:
        pass
    return names


def _match_rule(rule: dict, context: dict) -> bool:
    if not rule.get("enabled", True):
        return False
    cond = rule.get("condition") or {}
    ctype = str(cond.get("type") or "").strip().lower()

    if ctype == "app_opened":
        target = str(cond.get("app") or cond.get("process") or "").lower()
        opened = {x.lower() for x in (context.get("opened_apps") or [])}
        running = {x.lower() for x in (context.get("running_apps") or list(_process_names()))}
        return bool(target) and (target in opened or target in running)

    if ctype == "app_closed":
        target = str(cond.get("app") or cond.get("process") or "").lower()
        closed = {x.lower() for x in (context.get("closed_apps") or [])}
        running = {x.lower() for x in (context.get("running_apps") or list(_process_names()))}
        if closed:
            return target in closed
        # evaluate_now without closed list: true if not running
        return bool(target) and target not in running

    if ctype == "battery_below":
        threshold = float(cond.get("percent") or cond.get("threshold") or 20)
        level = context.get("battery")
        if level is None:
            level = _battery_percent()
        if level is None:
            return False
        return float(level) < threshold

    if ctype == "idle_minutes":
        minutes = float(cond.get("minutes") or 30)
        idle = context.get("idle_seconds")
        if idle is None:
            idle = _idle_seconds()
        if idle is None:
            return False
        return float(idle) >= minutes * 60.0

    if ctype == "time_window":
        # HH:MM-HH:MM local
        window = str(cond.get("window") or "")
        now = context.get("now_hhmm")
        if not now:
            from datetime import datetime
            now = datetime.now().strftime("%H:%M")
        try:
            start, end = window.split("-", 1)
            return start.strip() <= str(now) <= end.strip()
        except Exception:
            return False

    return False


def _fire_action(action: dict, player=None) -> str:
    kind = str(action.get("kind") or action.get("type") or "").lower()
    name = str(action.get("name") or action.get("target") or "").strip()
    params = dict(action.get("params") or {})
    try:
        if kind in ("routine", "routine_orchestrator"):
            import actions.productivity.routine_orchestrator as routine_orchestrator
            params.setdefault("action", "run")
            if name:
                params.setdefault("name", name)
            return routine_orchestrator.routine_orchestrator(parameters=params, player=player)
        if kind in ("mission", "mission_planner"):
            from .mission_planner import mission_planner
            params.setdefault("action", "plan_and_run")
            if name and not params.get("goal"):
                params["goal"] = name
            return mission_planner(parameters=params, player=player)
        if kind in ("tool", "action"):
            tool = str(action.get("tool") or name)
            mod = __import__(f"actions.{tool}", fromlist=["TOOL"])
            handler = mod.TOOL["handler"]
            try:
                return handler(parameters=params, player=player)
            except TypeError:
                return handler(params)
        return failed("context_triggers", f"unknown action kind: {kind}")
    except Exception as e:
        return failed("context_triggers", f"fire failed: {e}")


def run(parameters: Optional[dict] = None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or p.get("mode") or "list").strip().lower()
    data = _load()
    rules = data.setdefault("rules", [])

    if action in ("list", "show"):
        summary = ", ".join(
            f"{r.get('id')}:{r.get('name') or r.get('condition',{}).get('type')}:"
            f"{'on' if r.get('enabled', True) else 'off'}"
            for r in rules
        ) or "(none)"
        return done(
            "context_triggers",
            op="list",
            enabled=bool(data.get("enabled", True)),
            count=len(rules),
            rules=summary,
        )

    if action in ("add", "create"):
        name = str(p.get("name") or "").strip() or f"rule_{len(rules)+1}"
        cond_type = str(p.get("condition_type") or p.get("type") or "").strip().lower()
        if not cond_type:
            # allow JSON condition blob
            cond_raw = p.get("condition")
            if isinstance(cond_raw, str):
                try:
                    cond = json.loads(cond_raw)
                    cond_type = str(cond.get("type") or "")
                except Exception:
                    return ask("context_triggers", "Informe condition_type (app_opened|battery_below|idle_minutes|time_window)")
            elif isinstance(cond_raw, dict):
                cond = cond_raw
                cond_type = str(cond.get("type") or "")
            else:
                return ask("context_triggers", "Informe condition_type")
        else:
            cond = {"type": cond_type}
            if cond_type in ("app_opened", "app_closed"):
                app = str(p.get("app") or p.get("process") or "").strip()
                if not app:
                    return ask("context_triggers", "Qual app/processo monitorar?")
                cond["app"] = app
            elif cond_type == "battery_below":
                cond["percent"] = float(p.get("percent") or p.get("threshold") or 20)
            elif cond_type == "idle_minutes":
                cond["minutes"] = float(p.get("minutes") or 30)
            elif cond_type == "time_window":
                cond["window"] = str(p.get("window") or "09:00-18:00")
            else:
                return failed("context_triggers", f"condition_type desconhecido: {cond_type}")

        fire = p.get("fire") or p.get("action_target")
        if isinstance(fire, str):
            try:
                fire = json.loads(fire)
            except Exception:
                fire = {"kind": "routine", "name": fire}
        if not isinstance(fire, dict):
            kind = str(p.get("fire_kind") or "routine").lower()
            target = str(p.get("fire_name") or p.get("target") or "").strip()
            if not target:
                return ask("context_triggers", "O que disparar? (rotina/missão/tool)")
            fire = {"kind": kind, "name": target}

        rid = uuid.uuid4().hex[:8]
        rule = {
            "id": rid,
            "name": name,
            "enabled": True,
            "condition": cond,
            "action": fire,
            "created_at": time.time(),
        }
        with _lock:
            rules.append(rule)
            _save(data)
        return done("context_triggers", op="add", id=rid, name=name, condition=cond_type)

    if action in ("remove", "delete"):
        rid = str(p.get("id") or p.get("rule_id") or p.get("name") or "").strip()
        if not rid:
            return ask("context_triggers", "Qual id/nome da regra remover?")
        before = len(rules)
        rules[:] = [r for r in rules if r.get("id") != rid and r.get("name") != rid]
        if len(rules) == before:
            return failed("context_triggers", f"regra não encontrada: {rid}")
        with _lock:
            _save(data)
        return done("context_triggers", op="remove", id=rid)

    if action in ("enable", "disable"):
        rid = str(p.get("id") or p.get("name") or "").strip()
        if not rid:
            # global
            data["enabled"] = action == "enable"
            with _lock:
                _save(data)
            return done("context_triggers", op=action, global_enabled=data["enabled"])
        found = False
        for r in rules:
            if r.get("id") == rid or r.get("name") == rid:
                r["enabled"] = action == "enable"
                found = True
        if not found:
            return failed("context_triggers", f"regra não encontrada: {rid}")
        with _lock:
            _save(data)
        return done("context_triggers", op=action, id=rid)

    if action in ("evaluate_now", "evaluate", "check"):
        if not data.get("enabled", True):
            return done("context_triggers", op="evaluate_now", matched=0, note="globally disabled")
        context = {
            "opened_apps": p.get("opened_apps") or [],
            "closed_apps": p.get("closed_apps") or [],
            "running_apps": p.get("running_apps"),
            "battery": p.get("battery"),
            "idle_seconds": p.get("idle_seconds"),
            "now_hhmm": p.get("now_hhmm"),
        }
        # allow JSON context
        if isinstance(p.get("context"), str):
            try:
                context.update(json.loads(p["context"]))
            except Exception:
                pass
        elif isinstance(p.get("context"), dict):
            context.update(p["context"])

        matched = []
        results = []
        dry = str(p.get("dry_run") or "").lower() in ("1", "true", "yes")
        for rule in rules:
            if _match_rule(rule, context):
                matched.append(rule.get("id"))
                if dry:
                    results.append(f"{rule.get('id')}:matched")
                else:
                    out = _fire_action(rule.get("action") or {}, player=player)
                    results.append(f"{rule.get('id')}:{(out or '')[:80]}")
        return done(
            "context_triggers",
            op="evaluate_now",
            matched=len(matched),
            ids=",".join(matched) or "(none)",
            results=" | ".join(results) or "(none)",
            dry_run=dry,
        )

    return failed("context_triggers", f"action desconhecida: {action}")
