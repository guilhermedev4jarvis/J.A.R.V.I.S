"""mission_planner engine — plan, persist, chain-execute desktop missions."""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.outcome import ask, done, failed, started, unverified

_BASE = Path(__file__).resolve().parents[2]
_MISSIONS = _BASE / "memory" / "desktop_missions"
_MAX_STEPS = 8
_SENSITIVE_TOOLS = frozenset({
    "whatsapp_web", "send_message", "secure_vault_helper", "powershell_tool",
    "file_manager", "desktop_control", "desktop_agent", "computer_settings",
    "self_program", "intruder_alert", "network_manager", "power_profile_manager",
})
_lock = threading.Lock()
_running: dict[str, threading.Event] = {}  # mission_id -> cancel event


def _missions_dir() -> Path:
    _MISSIONS.mkdir(parents=True, exist_ok=True)
    return _MISSIONS


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def _mission_path(mission_id: str) -> Optional[Path]:
    d = _missions_dir()
    matches = sorted(d.glob(f"mission_*_{mission_id}.json"))
    if matches:
        return matches[-1]
    # allow full stem or prefix match
    for p in sorted(d.glob("mission_*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("id") == mission_id:
                return p
        except Exception:
            continue
    return None


def _save(mission: dict) -> Path:
    d = _missions_dir()
    mid = mission["id"]
    path = d / f"mission_{mission.get('created_ts', _ts())}_{mid}.json"
    # update in place if exists
    existing = _mission_path(mid)
    if existing is not None:
        path = existing
    path.write_text(json.dumps(mission, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load(mission_id: str) -> Optional[dict]:
    path = _mission_path(mission_id)
    if not path:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _list_missions(limit: int = 15) -> list[dict]:
    items = []
    for p in sorted(_missions_dir().glob("mission_*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            items.append({
                "id": data.get("id"),
                "goal": (data.get("goal") or "")[:120],
                "status": data.get("status"),
                "steps": len(data.get("steps") or []),
                "path": str(p.name),
            })
        except Exception:
            continue
    return items


def _speak(text: str, player=None) -> None:
    if not text:
        return
    if player:
        for attr in ("plugin_say", "say", "request_say"):
            fn = getattr(player, attr, None)
            if callable(fn):
                try:
                    fn(text)
                    return
                except Exception:
                    pass
    try:
        from core import tts as tts_mod
        tts_mod.create_tts_player({}).speak(text)
    except Exception:
        print(f"[mission_planner] TTS: {text}")


def _audit(event: str, detail: dict) -> None:
    try:
        from core import audit
        audit.log_event(event, detail)
    except Exception:
        pass


def _owner_gate_ok(tool_name: str, action: str = "") -> tuple[bool, str]:
    try:
        from core import owner_gate
        if hasattr(owner_gate, "require_unlocked_for_critical"):
            r = owner_gate.require_unlocked_for_critical(tool_name, action, camera=True)
            if isinstance(r, dict):
                return bool(r.get("accepted")), str(r.get("detail") or "owner_gate")
            return bool(r), "owner_gate"
        if hasattr(owner_gate, "is_critical") and owner_gate.is_critical(tool_name, action):
            if hasattr(owner_gate, "require_owner"):
                r = owner_gate.require_owner(method="face", camera=True)
                if isinstance(r, dict):
                    return bool(r.get("accepted")), str(r.get("detail") or "require_owner")
        return True, "ok"
    except Exception as e:
        # Fail closed for sensitive tools
        if tool_name in _SENSITIVE_TOOLS:
            return False, f"owner_gate error: {e}"
        return True, f"owner_gate skipped: {e}"


def _extract_json(text: str) -> Any:
    text = (text or "").strip()
    if not text:
        return None
    # fenced block
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```", text)
    if m:
        text = m.group(1)
    else:
        # first array or object
        for opener, closer in (("[", "]"), ("{", "}")):
            i = text.find(opener)
            j = text.rfind(closer)
            if i >= 0 and j > i:
                text = text[i : j + 1]
                break
    try:
        return json.loads(text)
    except Exception:
        return None


def _normalize_plan(raw: Any, goal: str) -> list[dict]:
    steps_in = []
    if isinstance(raw, dict):
        steps_in = raw.get("steps") or raw.get("plan") or []
    elif isinstance(raw, list):
        steps_in = raw
    if not isinstance(steps_in, list):
        raise ValueError("plan must be a list of steps")

    out = []
    for i, s in enumerate(steps_in[:_MAX_STEPS], 1):
        if not isinstance(s, dict):
            continue
        tool = str(s.get("tool_name") or s.get("tool") or s.get("name") or "").strip()
        if not tool:
            continue
        args = s.get("args") or s.get("parameters") or s.get("params") or {}
        if not isinstance(args, dict):
            args = {}
        requires = s.get("requires_owner_gate")
        if requires is None:
            requires = tool in _SENSITIVE_TOOLS
        out.append({
            "step_id": str(s.get("step_id") or f"s{i}"),
            "tool_name": tool,
            "args": args,
            "description": str(s.get("description") or s.get("desc") or tool),
            "requires_owner_gate": bool(requires),
            "status": "pending",
            "output": None,
            "error": None,
            "started_at": None,
            "finished_at": None,
        })
    if not out:
        raise ValueError("empty plan after normalization")
    if len(steps_in) > _MAX_STEPS:
        # truncate already applied; flag in description of last
        out[-1]["description"] += f" (plan truncated to {_MAX_STEPS} steps)"
    return out


def _heuristic_plan(goal: str) -> list[dict]:
    """Offline fallback when LLM is unavailable — keyword mapping for tests/air-gap."""
    g = goal.lower()
    steps = []
    sid = 1

    def add(tool, args, desc, sensitive=None):
        nonlocal sid
        sens = tool in _SENSITIVE_TOOLS if sensitive is None else sensitive
        steps.append({
            "step_id": f"s{sid}",
            "tool_name": tool,
            "args": args,
            "description": desc,
            "requires_owner_gate": sens,
            "status": "pending",
            "output": None,
            "error": None,
            "started_at": None,
            "finished_at": None,
        })
        sid += 1

    if any(k in g for k in ("pesquisa", "preço", "preco", "search", "busca", "rtx", "noticia")):
        add("web_search", {"query": goal[:200]}, "Pesquisar informações na web")
    if any(k in g for k in ("arquivo", "salva", "salvar", "resumo", "nota", "file")):
        add("quick_note", {"action": "add", "text": "{{previous_output}}", "notebook": "missions"},
            "Salvar resumo em nota local")
    if any(k in g for k in ("whatsapp", "avisa", "mensagem", "manda")):
        add("whatsapp_web", {"mode": "open"}, "Abrir WhatsApp para notificar", True)
    if any(k in g for k in ("clima", "tempo", "weather")):
        add("weather_report", {"cidade": "São Paulo"}, "Consultar clima")
    if not steps:
        add("web_search", {"query": goal[:200]}, "Pesquisar sobre o objetivo")
        add("quick_note", {"action": "add", "text": "{{previous_output}}", "notebook": "missions"},
            "Registrar resultado")
    return steps[:_MAX_STEPS]


def _llm_plan(goal: str) -> list[dict]:
    system = (
        "You are a mission planner for a desktop assistant. "
        f"Decompose the user goal into at most {_MAX_STEPS} ordered tool steps. "
        "Reply with ONLY valid JSON of the form: "
        '{"steps":[{"step_id":"s1","tool_name":"...","args":{},'
        '"description":"...","requires_owner_gate":false}]}. '
        "tool_name must be an existing JARVIS action name "
        "(web_search, whatsapp_web, quick_note, file_manager, open_app, "
        "weather_report, deep_research, send_message, clipboard_smart, "
        "focus_timer, system_health, desktop_control, ...). "
        "Use requires_owner_gate true for messaging, shell, file delete, vault."
    )
    prompt = f"Goal: {goal}\nJSON plan:"
    try:
        from core.llm_client import call_llm_text
        text = call_llm_text(prompt, system=system, timeout=60)
        raw = _extract_json(text)
        return _normalize_plan(raw, goal)
    except Exception as e:
        print(f"[mission_planner] LLM plan failed ({e}); using heuristic")
        return _heuristic_plan(goal)


def _inject_context(args: dict, previous_output: Optional[str]) -> dict:
    if not previous_output:
        return dict(args)
    out = {}
    for k, v in args.items():
        if isinstance(v, str) and "{{previous_output}}" in v:
            out[k] = v.replace("{{previous_output}}", previous_output[:4000])
        else:
            out[k] = v
    # common auto-fill if empty text fields
    if previous_output:
        for key in ("text", "message", "message_text", "content", "query", "note"):
            if key in out and (out[key] is None or str(out[key]).strip() in ("", "{{previous_output}}")):
                out[key] = previous_output[:4000]
    return out


def _run_tool(tool_name: str, params: dict, player=None) -> str:
    # Prefer live registry if discoverable; else import actions.<name>
    try:
        from core import action_loader
        # Try module-level last registry if main stored one — fallback import
    except Exception:
        pass
    try:
        mod = __import__(f"actions.{tool_name}", fromlist=["TOOL"])
        tool = getattr(mod, "TOOL", None)
        if not tool or not callable(tool.get("handler")):
            return failed("mission_planner", f"tool has no handler: {tool_name}")
        handler = tool["handler"]
        try:
            return handler(parameters=params, player=player)
        except TypeError:
            try:
                return handler(params, player=player)
            except TypeError:
                return handler(params)
    except Exception as e:
        return failed("mission_planner", f"invoke {tool_name}: {e}")


def _execute_mission(mission: dict, player=None, cancel: Optional[threading.Event] = None) -> dict:
    mid = mission["id"]
    mission["status"] = "running"
    mission["updated_at"] = time.time()
    _save(mission)
    _speak(f"Iniciando missão: {mission.get('goal', '')[:80]}", player)

    previous = mission.get("last_output")
    steps = mission.get("steps") or []
    for step in steps:
        if cancel is not None and cancel.is_set():
            mission["status"] = "cancelled"
            _save(mission)
            _audit("mission_cancelled", {"id": mid})
            return mission
        if step.get("status") in ("completed",):
            previous = step.get("output") or previous
            continue

        tool = step["tool_name"]
        step["status"] = "running"
        step["started_at"] = time.time()
        _save(mission)

        if step.get("requires_owner_gate") or tool in _SENSITIVE_TOOLS:
            ok, detail = _owner_gate_ok(tool)
            _audit("mission_owner_gate", {"id": mid, "tool": tool, "ok": ok, "detail": detail})
            if not ok:
                step["status"] = "blocked_by_security"
                step["error"] = detail
                step["finished_at"] = time.time()
                mission["status"] = "blocked_by_security"
                _save(mission)
                _speak("Missão bloqueada por segurança.", player)
                return mission

        args = _inject_context(dict(step.get("args") or {}), previous)
        try:
            result = _run_tool(tool, args, player=player)
        except Exception as e:
            result = failed(tool, str(e))

        step["finished_at"] = time.time()
        step["output"] = result
        # Treat outcome failed/blocked as step failure
        if isinstance(result, str) and result.startswith("status=failed"):
            step["status"] = "failed"
            step["error"] = result[:300]
            mission["status"] = "failed"
            mission["last_output"] = result
            _save(mission)
            _speak(f"Etapa falhou: {step.get('description')}", player)
            return mission
        step["status"] = "completed"
        step["error"] = None
        previous = result
        mission["last_output"] = result
        _save(mission)

    mission["status"] = "completed"
    mission["updated_at"] = time.time()
    _save(mission)
    _speak("Missão concluída.", player)
    _audit("mission_completed", {"id": mid, "steps": len(steps)})
    return mission


def create_plan(goal: str, *, execute: bool, player=None) -> str:
    goal = (goal or "").strip()
    if not goal:
        return ask("mission_planner", "Qual o objetivo da missão?")

    try:
        steps = _llm_plan(goal)
    except Exception as e:
        return failed("mission_planner", f"não foi possível gerar o plano: {e}")

    if len(steps) > _MAX_STEPS:
        return failed("mission_planner", f"plano excede {_MAX_STEPS} etapas")

    mid = _new_id()
    created = _ts()
    mission = {
        "id": mid,
        "goal": goal,
        "status": "planned",
        "created_ts": created,
        "created_at": time.time(),
        "updated_at": time.time(),
        "steps": steps,
        "last_output": None,
    }
    path = _save(mission)
    _audit("mission_planned", {"id": mid, "steps": len(steps), "execute": execute})

    if not execute:
        summary = "; ".join(f"{s['step_id']}:{s['tool_name']}" for s in steps)
        return done(
            "mission_planner",
            op="plan_only",
            mission_id=mid,
            steps=len(steps),
            plan=summary,
            path=path.name,
        )

    # run async so the tool can return started quickly for long missions
    cancel = threading.Event()
    with _lock:
        _running[mid] = cancel

    def _bg():
        try:
            _execute_mission(mission, player=player, cancel=cancel)
        finally:
            with _lock:
                _running.pop(mid, None)

    threading.Thread(target=_bg, daemon=True, name=f"mission-{mid}").start()
    return started(
        "mission_planner",
        op="plan_and_run",
        mission_id=mid,
        steps=len(steps),
        path=path.name,
    )


def resume_mission(mission_id: str, player=None) -> str:
    mission_id = (mission_id or "").strip()
    if not mission_id:
        return ask("mission_planner", "Qual o id da missão para retomar?")
    mission = _load(mission_id)
    if not mission:
        return failed("mission_planner", f"missão não encontrada: {mission_id}")
    if mission.get("status") == "running":
        return unverified("mission_planner", "missão já está em execução", mission_id=mission_id)
    # reset failed/blocked pending from first non-completed
    for step in mission.get("steps") or []:
        if step.get("status") in ("failed", "blocked_by_security", "running"):
            step["status"] = "pending"
            step["error"] = None
    mission["status"] = "planned"
    _save(mission)

    cancel = threading.Event()
    with _lock:
        _running[mission_id] = cancel

    def _bg():
        try:
            _execute_mission(mission, player=player, cancel=cancel)
        finally:
            with _lock:
                _running.pop(mission_id, None)

    threading.Thread(target=_bg, daemon=True, name=f"mission-resume-{mission_id}").start()
    return started("mission_planner", op="resume", mission_id=mission_id)


def cancel_mission(mission_id: str) -> str:
    mission_id = (mission_id or "").strip()
    if not mission_id:
        return ask("mission_planner", "Qual o id da missão para cancelar?")
    with _lock:
        ev = _running.get(mission_id)
        if ev:
            ev.set()
    mission = _load(mission_id)
    if mission:
        mission["status"] = "cancelled"
        mission["updated_at"] = time.time()
        _save(mission)
    _audit("mission_cancel_requested", {"id": mission_id})
    return done("mission_planner", op="cancel", mission_id=mission_id)


def status_mission(mission_id: str = "") -> str:
    mission_id = (mission_id or "").strip()
    if not mission_id:
        items = _list_missions()
        summary = " | ".join(
            f"{i.get('id')}:{i.get('status')}:{i.get('steps')}steps" for i in items
        ) or "(none)"
        return done("mission_planner", op="list", count=len(items), missions=summary)
    mission = _load(mission_id)
    if not mission:
        return failed("mission_planner", f"missão não encontrada: {mission_id}")
    steps = mission.get("steps") or []
    detail = ", ".join(f"{s.get('step_id')}:{s.get('status')}" for s in steps)
    return done(
        "mission_planner",
        op="status",
        mission_id=mission_id,
        status=mission.get("status"),
        goal=mission.get("goal"),
        steps_detail=detail,
    )


def run(parameters: Optional[dict] = None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or p.get("mode") or "plan_and_run").strip().lower()
    goal = str(p.get("goal") or p.get("objective") or p.get("task") or p.get("prompt") or "").strip()
    mission_id = str(p.get("mission_id") or p.get("id") or "").strip()

    try:
        if action in ("plan_and_run", "run", "start", "execute"):
            return create_plan(goal, execute=True, player=player)
        if action in ("plan_only", "plan"):
            return create_plan(goal, execute=False, player=player)
        if action in ("resume", "continue"):
            return resume_mission(mission_id or goal, player=player)
        if action in ("status", "list", "show"):
            return status_mission(mission_id)
        if action in ("cancel", "stop", "abort"):
            return cancel_mission(mission_id or goal)
        return failed(
            "mission_planner",
            f"action desconhecida: {action}. Use plan_and_run|plan_only|resume|status|list|cancel",
        )
    except Exception as e:
        return failed("mission_planner", f"erro: {e}")
