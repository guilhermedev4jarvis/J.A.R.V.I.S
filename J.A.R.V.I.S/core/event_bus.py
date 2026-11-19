"""core/event_bus.py — thread-safe Pub/Sub + chained rules (config/event_rules.json)."""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

_BASE = Path(__file__).resolve().parents[1]
_RULES_PATH = _BASE / "config" / "event_rules.json"

Subscriber = Callable[[str, dict], None]


class EventBus:
    _instance: Optional["EventBus"] = None
    _inst_lock = threading.Lock()

    def __init__(self) -> None:
        self._subs: dict[str, list[Subscriber]] = {}
        self._lock = threading.Lock()
        self._cooldown: dict[str, float] = {}
        self._facts: dict[str, Any] = {}  # for AND conditions across events
        self._facts_lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="event-bus")
        self._rules: list[dict] = []
        self._history: list[dict] = []
        self._history_lock = threading.Lock()
        self._history_max = 200
        self.reload_rules()

    @classmethod
    def get(cls) -> "EventBus":
        with cls._inst_lock:
            if cls._instance is None:
                cls._instance = EventBus()
            return cls._instance

    def reload_rules(self) -> int:
        if not _RULES_PATH.is_file():
            self._rules = []
            return 0
        try:
            data = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
            self._rules = list(data.get("rules") or [])
        except Exception:
            self._rules = []
        return len(self._rules)

    def subscribe(self, event: str, fn: Subscriber) -> None:
        with self._lock:
            self._subs.setdefault(event, []).append(fn)

    def set_fact(self, key: str, value: Any, ttl: float = 600.0) -> None:
        with self._facts_lock:
            self._facts[key] = {"value": value, "exp": time.monotonic() + ttl}

    def get_fact(self, key: str) -> Any:
        with self._facts_lock:
            item = self._facts.get(key)
            if not item:
                return None
            if time.monotonic() > float(item.get("exp") or 0):
                self._facts.pop(key, None)
                return None
            return item.get("value")

    def publish(self, event: str, payload: Optional[dict] = None) -> None:
        payload = dict(payload or {})
        payload.setdefault("event", event)
        payload.setdefault("ts", time.time())
        with self._history_lock:
            self._history.append({"event": event, **payload})
            if len(self._history) > self._history_max:
                self._history = self._history[-self._history_max:]
        self._audit("event_publish", {"event": event, **{k: payload.get(k) for k in list(payload)[:8]}})
        # store fact synchronously so compound AND rules see prior events
        self.set_fact(f"evt:{event}", payload, ttl=900.0)
        with self._lock:
            subs = list(self._subs.get(event, []))
            subs += list(self._subs.get("*", []))
        for fn in subs:
            self._pool.submit(self._safe_call, fn, event, payload)
        # evaluate chained rules (async)
        self._pool.submit(self._eval_rules, event, payload)

    def _safe_call(self, fn: Subscriber, event: str, payload: dict) -> None:
        try:
            fn(event, payload)
        except Exception as e:
            self._audit("event_subscriber_err", {"event": event, "error": str(e)[:160]})

    def _cooldown_ok(self, rule_id: str, seconds: float) -> bool:
        now = time.monotonic()
        last = self._cooldown.get(rule_id, 0.0)
        if now - last < max(0.0, seconds):
            return False
        self._cooldown[rule_id] = now
        return True

    def _match(self, rule: dict, event: str, payload: dict) -> bool:
        when = rule.get("when") or {}
        if "slide" in when or "sliding" in when:
            return self.match_sliding(event, payload, when)
        # single event
        if "event" in when:
            if when["event"] != event:
                return False
            for k, v in (when.get("match") or {}).items():
                if payload.get(k) != v:
                    return False
            return True
        # compound AND of recent facts / current event
        if "all" in when:
            for cond in when["all"]:
                ev = cond.get("event")
                if ev == event:
                    for k, v in (cond.get("match") or {}).items():
                        if payload.get(k) != v:
                            return False
                else:
                    fact = self.get_fact(f"evt:{ev}")
                    if not fact:
                        return False
                    for k, v in (cond.get("match") or {}).items():
                        if (fact or {}).get(k) != v:
                            return False
            return True
        if "any" in when:
            for cond in when["any"]:
                if self._match({"when": cond}, event, payload):
                    return True
            return False
        return False

    def _eval_rules(self, event: str, payload: dict) -> None:
        for rule in list(self._rules):
            if not rule.get("enabled", True):
                continue
            try:
                if not self._match(rule, event, payload):
                    continue
                rid = str(rule.get("id") or rule.get("name") or "rule")
                cd = float(rule.get("cooldown_sec") or 30)
                if not self._cooldown_ok(rid, cd):
                    continue
                self._audit("event_rule_fire", {"rule": rid, "event": event})
                for action in rule.get("actions") or []:
                    self._run_action(action, payload, rid)
            except Exception as e:
                self._audit("event_rule_err", {"error": str(e)[:160]})

    def _run_action(self, action: dict, payload: dict, rule_id: str) -> None:
        kind = str(action.get("type") or action.get("tool") or "").lower()
        params = dict(action.get("params") or {})
        # merge payload fields if requested
        for k in action.get("from_payload") or []:
            if k in payload:
                params[k] = payload[k]
        try:
            if kind in ("sentinel_patrol", "actions.security.sentinel_patrol"):
                import actions.security.sentinel_patrol as sentinel_patrol
                sentinel_patrol.sentinel_patrol(parameters=params or {"action": "start_away"})
            elif kind in ("anti_sabotagem_energia",):
                import actions.security.anti_sabotagem_energia as anti_sabotagem_energia
                anti_sabotagem_energia.anti_sabotagem_energia(parameters=params or {"action": "start"})
            elif kind in ("smart_home",):
                try:
                    import actions.smarthome.smart_home as smart_home
                    smart_home.smart_home(parameters=params)
                except Exception as e:
                    self._audit("event_smart_home_err", {"error": str(e)[:120]})
            elif kind in ("protocolo_dissuasao",):
                try:
                    import actions.security.protocolo_dissuasao as protocolo_dissuasao
                    protocolo_dissuasao.protocolo_dissuasao(parameters=params or {"action": "ativar"})
                except Exception as e:
                    self._audit("event_dissuasao_err", {"error": str(e)[:120]})
            elif kind in ("simulador_presenca",):
                try:
                    import actions.smarthome.simulador_presenca as simulador_presenca
                    simulador_presenca.simulador_presenca(parameters=params)
                except Exception as e:
                    self._audit("event_sim_presenca_err", {"error": str(e)[:120]})
            elif kind in ("power_profile_manager",):
                try:
                    import actions.system.power_profile_manager as power_profile_manager
                    power_profile_manager.power_profile_manager(parameters=params)
                except Exception as e:
                    self._audit("event_power_profile_err", {"error": str(e)[:120]})
            elif kind in ("resource_governor",):
                try:
                    import actions.system.resource_governor as resource_governor
                    resource_governor.resource_governor(parameters=params)
                except Exception as e:
                    self._audit("event_resource_gov_err", {"error": str(e)[:120]})
            elif kind in ("offline",):
                import actions.ai_core.offline as offline
                offline.offline(parameters=params or {"action": "enable"})
            elif kind in ("telegram", "telegram_commander", "notify_telegram"):
                from actions.security._security_vision import send_telegram
                msg = params.get("message") or action.get("message") or f"Evento regra {rule_id}"
                # format with payload
                try:
                    msg = msg.format(**payload)
                except Exception:
                    pass
                send_telegram(msg, markdown=True)
            elif kind in ("set_fact",):
                self.set_fact(str(params.get("key")), params.get("value"), float(params.get("ttl") or 180))
            elif kind in ("pause_intrusion",):
                self.set_fact("intrusion_pause_gate", True, float(params.get("ttl") or 180))
            else:
                mod_name = kind
                try:
                    mod = __import__(f"actions.{mod_name}", fromlist=["*"])
                    tool = getattr(mod, "TOOL", None)
                    if tool and callable(tool.get("handler")):
                        tool["handler"](parameters=params)
                    else:
                        self.push_dlq(rule_id, action, f"unknown_kind:{kind}")
                except Exception as e:
                    self._audit("event_action_unknown", {"kind": kind, "error": str(e)[:120]})
                    self.push_dlq(rule_id, action, str(e))
            self._audit("event_action_ok", {"rule": rule_id, "kind": kind})
        except Exception as e:
            self._audit("event_action_err", {"rule": rule_id, "kind": kind, "error": str(e)[:160]})
            self.push_dlq(rule_id, action, str(e))

    def recent_events(self, limit: int = 50) -> list[dict]:
        if not hasattr(self, "_history"):
            self._history = []
            self._history_lock = threading.Lock()
            self._history_max = 200
        with self._history_lock:
            return list(self._history[-max(1, int(limit)):])


    def sliding_window_count(self, event: str, window_sec: float) -> int:
        """Count how many times event appeared in the last window_sec."""
        now = time.time()
        with self._history_lock:
            return sum(
                1
                for e in self._history
                if e.get("event") == event and (now - float(e.get("ts") or 0)) <= window_sec
            )

    def match_sliding(self, event: str, payload: dict, when: dict) -> bool:
        """when may include slide: {event, count, window_sec} and optional match."""
        slide = when.get("slide") or when.get("sliding")
        if not slide:
            return False
        need = int(slide.get("count") or 1)
        window = float(slide.get("window_sec") or 300)
        ev = slide.get("event") or event
        # include current
        n = self.sliding_window_count(ev, window)
        if event == ev:
            n = max(n, 1)  # current publish counted via history already if recorded first
        return n >= need

    def persist_state(self, path: Optional[Path] = None) -> None:
        path = path or (Path(__file__).resolve().parents[1] / "memory" / "event_bus_state.json")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "cooldown": dict(self._cooldown),
                "history_tail": self.recent_events(50),
                "metrics": getattr(self, "_metrics", {}),
            }
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def load_state(self, path: Optional[Path] = None) -> None:
        path = path or (Path(__file__).resolve().parents[1] / "memory" / "event_bus_state.json")
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._cooldown.update({k: float(v) for k, v in (data.get("cooldown") or {}).items()})
            with self._history_lock:
                for e in data.get("history_tail") or []:
                    if isinstance(e, dict):
                        self._history.append(e)
            self._metrics = dict(data.get("metrics") or {})
        except Exception:
            pass

    def push_dlq(self, rule_id: str, action: dict, error: str) -> None:
        if not hasattr(self, "_dlq"):
            self._dlq = []
        self._dlq.append({"rule": rule_id, "action": action, "error": error, "ts": time.time()})
        self._dlq = self._dlq[-100:]
        self._audit("event_dlq", {"rule": rule_id, "error": error[:160]})

    @staticmethod
    def _audit(kind: str, extra: dict) -> None:
        try:
            from core import audit as audit_mod
            audit_mod.log_event(kind, tool="event_bus", extra=extra)
        except Exception:
            pass


def get_bus() -> EventBus:
    return EventBus.get()


def publish(event: str, **payload: Any) -> None:
    get_bus().publish(event, payload)


def recent_events(limit: int = 50) -> list[dict]:
    return get_bus().recent_events(limit)
