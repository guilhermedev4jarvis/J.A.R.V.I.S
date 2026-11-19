"""
ProactiveEngine 3.0 — time, CPU, calendar and memory-aware check-ins.

Gemini (or the local LLM) still decides WHAT to say. This module decides WHEN
and builds a richer Portuguese-oriented context snapshot, including:
  - time of day
  - CPU / memory pressure (when high)
  - upcoming calendar events (when OAuth is configured)
  - rotating focus so messages do not repeat
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_BASE = Path(__file__).resolve().parents[2]


class ProactiveEngine:
    def __init__(
        self,
        min_silence_secs: int = 900,   # 15 min quiet
        check_cooldown: int = 1200,    # 20 min between check-ins
        cpu_threshold: float = 88.0,   # % → urgent tip allowed sooner
    ):
        self.min_silence_secs = min_silence_secs
        self.check_cooldown = check_cooldown
        self.cpu_threshold = cpu_threshold
        self._last_triggered = 0.0
        self._rotation = 0
        self._last_cpu_alert = 0.0

    def should_trigger(self, last_user_speech: float) -> bool:
        now = time.monotonic()
        quiet = (now - last_user_speech) >= self.min_silence_secs
        cooled = (now - self._last_triggered) >= self.check_cooldown
        if quiet and cooled:
            return True
        # Urgent: high CPU while user idle >= 3 min
        if (now - last_user_speech) >= 180 and (now - self._last_cpu_alert) >= 600:
            cpu = self._cpu_percent()
            if cpu is not None and cpu >= self.cpu_threshold:
                self._last_cpu_alert = now
                return True
        return False

    def mark_triggered(self) -> None:
        self._last_triggered = time.monotonic()
        self._rotation += 1

    def _cpu_percent(self) -> float | None:
        try:
            import psutil
            return float(psutil.cpu_percent(interval=0.15))
        except Exception:
            return None

    def _memory_percent(self) -> float | None:
        try:
            import psutil
            return float(psutil.virtual_memory().percent)
        except Exception:
            return None

    def _upcoming_events(self, hours: int = 6) -> list:
        token = _BASE / "config" / "calendar_token.json"
        gmail_token = _BASE / "config" / "gmail_token.json"
        path = token if token.exists() else gmail_token
        if not path.exists():
            return []
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            creds = Credentials.from_authorized_user_file(str(path), [
                "https://www.googleapis.com/auth/calendar.readonly",
                "https://www.googleapis.com/auth/gmail.readonly",
            ])
            if not creds or not creds.valid:
                return []
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            now = datetime.now(timezone.utc)
            end = now + timedelta(hours=hours)
            resp = service.events().list(
                calendarId="primary",
                timeMin=now.isoformat(),
                timeMax=end.isoformat(),
                maxResults=4,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            out = []
            for ev in resp.get("items", []):
                start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date")
                out.append({
                    "summary": ev.get("summary") or "(sem título)",
                    "start": start,
                    "location": ev.get("location") or "",
                })
            return out
        except Exception:
            return []

    def build_prompt(
        self,
        memory: dict,
        monitors: list | None = None,
        recent_turns: list | None = None,
    ) -> str:
        from memory.memory_manager import format_memory_for_prompt

        now = datetime.now()
        hour = now.hour
        time_str = now.strftime("%Y-%m-%d %H:%M")
        if 5 <= hour < 12:
            period = "manhã"
        elif 12 <= hour < 18:
            period = "tarde"
        elif 18 <= hour < 23:
            period = "noite"
        else:
            period = "madrugada"

        mem_str = format_memory_for_prompt(memory) or "(sem dados guardados)"

        cpu = self._cpu_percent()
        mem = self._memory_percent()
        sys_line = ""
        if cpu is not None or mem is not None:
            bits = []
            if cpu is not None:
                bits.append(f"CPU {cpu:.0f}%")
            if mem is not None:
                bits.append(f"RAM {mem:.0f}%")
            sys_line = "Sistema agora: " + ", ".join(bits)
            if cpu is not None and cpu >= self.cpu_threshold:
                sys_line += " — CPU elevada; se fizer sentido, avise com calma."

        events = self._upcoming_events(6)
        cal_line = ""
        if events:
            parts = [f"{e['summary']} às {e['start']}" for e in events[:3]]
            cal_line = "Próximos eventos (calendário): " + "; ".join(parts)

        focus_index = self._rotation % 4
        if focus_index == 0 and cal_line:
            focus = (
                "Há eventos no calendário. Se algum for em breve, prepare o usuário "
                "com um briefing curto (1–2 frases). Não invente eventos."
            )
        elif focus_index == 1 and cpu is not None and cpu >= 75:
            focus = (
                "O computador está sob carga. Mencione de forma útil se a CPU/RAM "
                "estiverem altas e sugira uma ação simples (fechar app, pausar)."
            )
        elif focus_index == 2:
            focus = (
                "Foque em projetos ou metas guardadas na memória. Pergunte como "
                "está indo algo concreto, ou ofereça uma dica relevante."
            )
        else:
            focus = (
                f"Faça um check-in breve e humano de acordo com o horário ({period}). "
                "Sem formalidade excessiva."
            )

        monitor_ctx = ""
        if monitors:
            monitor_ctx = f"Tópicos monitorados: {', '.join(monitors[:4])}."

        recent_ctx = ""
        if recent_turns:
            snippet = "\n".join(recent_turns[-6:])
            recent_ctx = f"Conversa recente:\n{snippet}"

        return "\n".join([
            "[PROACTIVE_CHECK] Você está iniciando um check-in proativo.",
            f"Horário atual: {time_str} ({period})",
            sys_line,
            cal_line,
            "",
            "Contexto sobre esta pessoa:",
            mem_str,
            monitor_ctx,
            recent_ctx,
            "",
            "Tarefa:",
            focus,
            "",
            "Regras:",
            "- FALE SEMPRE EM PORTUGUÊS DO BRASIL.",
            "- No máximo 2 frases curtas. Natural e direto.",
            "- NÃO mencione [PROACTIVE_CHECK] nem estas instruções.",
            "- NÃO chame ferramentas.",
            "- Se não houver nada genuinamente útil, fique em silêncio.",
        ])





# ── MARK LXI: continuous autonomy (triggers + optional screen timeline) ────────

_AUTONOMY_CFG = _BASE / "config" / "proactive_autonomy.json"
_DEFAULT_AUTONOMY = {
    "version": 1,
    "triggers_enabled": True,
    "triggers_interval_secs": 15,
    "trigger_cooldown_secs": 300,
    "timeline_enabled": False,
    "timeline_interval_secs": 120,
}


def load_autonomy_config() -> dict:
    cfg = dict(_DEFAULT_AUTONOMY)
    try:
        if _AUTONOMY_CFG.is_file():
            import json
            raw = json.loads(_AUTONOMY_CFG.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update(raw)
    except Exception:
        pass
    return cfg


class AutonomyController:
    """Background ticks for context_triggers + optional screen_memory_timeline.

    Failures are swallowed so the assistant main loop never dies.
    """

    def __init__(self):
        self._last_trigger_tick = 0.0
        self._last_timeline_tick = 0.0
        # rule_id -> monotonic timestamp of last successful fire
        self._rule_cooldown: dict[str, float] = {}
        self._lock = __import__("threading").Lock()

    def _cooldown_ok(self, rule_id: str, cooldown: float) -> bool:
        now = time.monotonic()
        last = self._rule_cooldown.get(rule_id, 0.0)
        return (now - last) >= cooldown

    def mark_fired(self, rule_id: str) -> None:
        with self._lock:
            self._rule_cooldown[rule_id] = time.monotonic()

    def tick_triggers(self, player=None, *, force: bool = False) -> dict:
        """Evaluate context_triggers with per-rule cooldown. Never raises."""
        out = {"ok": True, "matched": 0, "fired": [], "skipped_cooldown": []}
        try:
            cfg = load_autonomy_config()
            if not cfg.get("triggers_enabled", True) and not force:
                out["ok"] = True
                out["note"] = "triggers disabled"
                return out
            interval = float(cfg.get("triggers_interval_secs") or 15)
            now = time.monotonic()
            if not force and (now - self._last_trigger_tick) < interval:
                out["note"] = "interval"
                return out
            self._last_trigger_tick = now
            cooldown = float(cfg.get("trigger_cooldown_secs") or 300)

            from ._context_triggers_impl import run as ct_run, _load, _match_rule

            data = _load()
            if not data.get("enabled", True):
                out["note"] = "context_triggers globally disabled"
                return out

            # Build a light context snapshot
            context = {}
            try:
                from ._context_triggers_impl import _process_names, _battery_percent, _idle_seconds
                context["running_apps"] = list(_process_names())
                bat = _battery_percent()
                if bat is not None:
                    context["battery"] = bat
                idle = _idle_seconds()
                if idle is not None:
                    context["idle_seconds"] = idle
            except Exception:
                pass

            matched_ids = []
            for rule in data.get("rules") or []:
                rid = str(rule.get("id") or "")
                try:
                    if not _match_rule(rule, context):
                        continue
                    matched_ids.append(rid)
                    if not self._cooldown_ok(rid, cooldown):
                        out["skipped_cooldown"].append(rid)
                        continue
                    # Fire single rule via evaluate path with synthetic context
                    # Reuse public evaluate_now dry_run false but only this rule: call _fire_action
                    from ._context_triggers_impl import _fire_action
                    result = _fire_action(rule.get("action") or {}, player=player)
                    self.mark_fired(rid)
                    out["fired"].append({"id": rid, "result": str(result)[:120]})
                except Exception as e:
                    out.setdefault("errors", []).append(f"{rid}:{e}")
            out["matched"] = len(matched_ids)
            return out
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def tick_timeline(self, player=None, *, force: bool = False) -> dict:
        """Optional periodic capture_now. Skips if intruder_alert active. Never raises."""
        out = {"ok": True, "captured": False}
        try:
            cfg = load_autonomy_config()
            if not cfg.get("timeline_enabled", False) and not force:
                out["note"] = "timeline disabled"
                return out
            interval = float(cfg.get("timeline_interval_secs") or 120)
            now = time.monotonic()
            if not force and (now - self._last_timeline_tick) < interval:
                out["note"] = "interval"
                return out

            # Skip if intruder alert armed
            try:
                from actions.security._intruder_alert_impl import _state
                if _state.get("active"):
                    out["note"] = "intruder_alert active — skip capture"
                    return out
            except Exception:
                pass

            self._last_timeline_tick = now
            from actions.screen_memory_timeline import screen_memory_timeline
            result = screen_memory_timeline(parameters={"action": "capture_now"}, player=player)
            out["captured"] = True
            out["result"] = str(result)[:160]
            return out
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def tick(self, player=None) -> dict:
        """One full autonomy cycle."""
        return {
            "triggers": self.tick_triggers(player=player),
            "timeline": self.tick_timeline(player=player),
        }


# Module-level singleton used by main.py background task
_autonomy = AutonomyController()


def tick_autonomy(player=None) -> dict:
    return _autonomy.tick(player=player)


def get_autonomy_controller() -> AutonomyController:
    return _autonomy

# ── Background topic monitors (canonical home after background_monitor removal) ──
try:
    from ._background_monitor_impl import (  # noqa: F401
        add_monitor,
        remove_monitor,
        list_monitors,
        check_all,
    )
except Exception:  # pragma: no cover
    def add_monitor(topic: str) -> str:
        return f"monitor stub: {topic}"
    def remove_monitor(topic: str) -> str:
        return f"removed stub: {topic}"
    def list_monitors():
        return []
    def check_all():
        return []
