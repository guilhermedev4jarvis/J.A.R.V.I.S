"""
resource_governor — automatic resource management for JARVIS itself.

Observes system load (CPU, RAM, battery) and applies graceful degradation:
  - lowers priority / frequency of background monitors
  - suggests pausing the 3D avatar / animations
  - throttles proactive checks
  - limits concurrent heavy actions

Does NOT kill processes or force changes that require user confirmation for
destructive operations. State is stored in config/resource_governor.json.
"""
from __future__ import annotations

import json
import platform
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from core.outcome import done, failed, ask

_BASE = Path(__file__).resolve().parents[2]
_STATE_PATH = _BASE / "config" / "resource_governor.json"
_lock = threading.Lock()

_OS = platform.system()

# Thresholds (percent)
_CPU_HIGH = 75.0
_CPU_CRIT = 90.0
_MEM_HIGH = 80.0
_MEM_CRIT = 92.0
_BATTERY_LOW = 20.0


def _has_psutil() -> bool:
    try:
        import psutil  # noqa: F401
        return True
    except ImportError:
        return False


def _load_state() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "mode": "auto",          # auto | performance | balanced | economy | manual
            "avatar_paused": False,
            "proactive_interval_sec": 60,
            "max_heavy_actions": 2,
            "background_priority": "normal",  # normal | low | paused
            "last_applied": None,
            "history": [],
        }


def _save_state(data: dict) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _STATE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _sample() -> dict[str, Any]:
    """Take a quick system sample."""
    import psutil

    cpu = float(psutil.cpu_percent(interval=0.2))
    mem = psutil.virtual_memory()
    battery = None
    try:
        bat = psutil.sensors_battery()
        if bat is not None:
            battery = {
                "percent": bat.percent,
                "plugged": bat.power_plugged,
            }
    except Exception:
        pass

    # Own process footprint
    self_rss_mb = 0.0
    try:
        p = psutil.Process()
        self_rss_mb = round(p.memory_info().rss / (1024 * 1024), 1)
    except Exception:
        pass

    return {
        "cpu_percent": round(cpu, 1),
        "memory_percent": round(mem.percent, 1),
        "memory_available_gb": round(mem.available / (1024 ** 3), 2),
        "self_rss_mb": self_rss_mb,
        "battery": battery,
    }


def _decide_mode(sample: dict) -> str:
    """Pick a degradation level from the sample."""
    cpu = sample["cpu_percent"]
    mem = sample["memory_percent"]
    bat = sample.get("battery") or {}

    # Critical
    if cpu >= _CPU_CRIT or mem >= _MEM_CRIT:
        return "economy"
    if bat and not bat.get("plugged") and bat.get("percent", 100) <= _BATTERY_LOW:
        return "economy"

    # High load
    if cpu >= _CPU_HIGH or mem >= _MEM_HIGH:
        return "balanced"

    return "performance"


def _apply_mode(mode: str, state: dict) -> dict:
    """Translate mode into concrete settings."""
    if mode == "performance":
        state["avatar_paused"] = False
        state["proactive_interval_sec"] = 45
        state["max_heavy_actions"] = 4
        state["background_priority"] = "normal"
    elif mode == "balanced":
        state["avatar_paused"] = False
        state["proactive_interval_sec"] = 90
        state["max_heavy_actions"] = 2
        state["background_priority"] = "low"
    elif mode == "economy":
        state["avatar_paused"] = True
        state["proactive_interval_sec"] = 180
        state["max_heavy_actions"] = 1
        state["background_priority"] = "paused"
    # "manual" keeps whatever the user set
    state["mode"] = mode
    state["last_applied"] = datetime.now().isoformat(timespec="seconds")
    return state


def resource_governor(parameters: dict | None = None, **_ctx) -> str:
    if not _has_psutil():
        return failed("resource_governor", "psutil is required")

    params = parameters or {}
    action = (params.get("action") or "status").strip().lower()

    with _lock:
        state = _load_state()

        # ── status ────────────────────────────────────────────────────────
        if action in ("status", "report", "check"):
            sample = _sample()
            suggested = _decide_mode(sample)
            return done(
                "resource_governor",
                action="status",
                current_mode=state.get("mode", "auto"),
                suggested_mode=suggested,
                avatar_paused=state.get("avatar_paused", False),
                proactive_interval_sec=state.get("proactive_interval_sec", 60),
                max_heavy_actions=state.get("max_heavy_actions", 2),
                background_priority=state.get("background_priority", "normal"),
                cpu_percent=sample["cpu_percent"],
                memory_percent=sample["memory_percent"],
                memory_available_gb=sample["memory_available_gb"],
                jarvis_rss_mb=sample["self_rss_mb"],
                battery=sample.get("battery"),
                last_applied=state.get("last_applied"),
            )

        # ── auto (observe + apply) ────────────────────────────────────────
        if action in ("auto", "apply", "govern", "run"):
            sample = _sample()
            if state.get("mode") == "manual":
                return done(
                    "resource_governor",
                    action="auto",
                    note="mode is manual — no automatic change applied",
                    current_mode="manual",
                    cpu_percent=sample["cpu_percent"],
                    memory_percent=sample["memory_percent"],
                )

            new_mode = _decide_mode(sample)
            old_mode = state.get("mode", "auto")
            state = _apply_mode(new_mode, state)

            # Keep a short history
            hist = state.get("history") or []
            hist.append({
                "at": state["last_applied"],
                "from": old_mode,
                "to": new_mode,
                "cpu": sample["cpu_percent"],
                "mem": sample["memory_percent"],
            })
            state["history"] = hist[-20:]
            _save_state(state)

            return done(
                "resource_governor",
                action="auto",
                previous_mode=old_mode,
                new_mode=new_mode,
                avatar_paused=state["avatar_paused"],
                proactive_interval_sec=state["proactive_interval_sec"],
                max_heavy_actions=state["max_heavy_actions"],
                background_priority=state["background_priority"],
                cpu_percent=sample["cpu_percent"],
                memory_percent=sample["memory_percent"],
                jarvis_rss_mb=sample["self_rss_mb"],
            )

        # ── set mode manually ─────────────────────────────────────────────
        if action in ("set", "mode", "set_mode"):
            mode = (params.get("mode") or "").strip().lower()
            if mode not in ("auto", "performance", "balanced", "economy", "manual"):
                return ask(
                    "resource_governor",
                    "which mode?",
                    options="auto, performance, balanced, economy, manual",
                )
            if mode == "auto":
                # Immediately evaluate
                sample = _sample()
                decided = _decide_mode(sample)
                state = _apply_mode(decided, state)
                state["mode"] = "auto"  # stay in auto
            elif mode == "manual":
                state["mode"] = "manual"
            else:
                state = _apply_mode(mode, state)
                state["mode"] = "manual"  # user forced a specific profile
            _save_state(state)
            return done(
                "resource_governor",
                action="set",
                mode=state["mode"],
                avatar_paused=state.get("avatar_paused"),
                proactive_interval_sec=state.get("proactive_interval_sec"),
                max_heavy_actions=state.get("max_heavy_actions"),
                background_priority=state.get("background_priority"),
            )

        # ── pause / resume avatar ─────────────────────────────────────────
        if action in ("pause_avatar", "avatar_off"):
            state["avatar_paused"] = True
            state["mode"] = "manual"
            _save_state(state)
            return done("resource_governor", action="pause_avatar", avatar_paused=True)

        if action in ("resume_avatar", "avatar_on"):
            state["avatar_paused"] = False
            _save_state(state)
            return done("resource_governor", action="resume_avatar", avatar_paused=False)

        # ── throttle proactive ────────────────────────────────────────────
        if action in ("throttle", "set_interval"):
            try:
                sec = int(params.get("seconds") or params.get("interval") or 90)
            except (TypeError, ValueError):
                return failed("resource_governor", "seconds must be an integer")
            sec = max(15, min(sec, 600))
            state["proactive_interval_sec"] = sec
            state["mode"] = "manual"
            _save_state(state)
            return done(
                "resource_governor",
                action="throttle",
                proactive_interval_sec=sec,
            )

        return ask(
            "resource_governor",
            "what should I do?",
            options="status, auto, set (mode=...), pause_avatar, resume_avatar, throttle",
        )


_LEGACY_TOOL = {
    "name": "resource_governor",
    "description": (
        "Governs JARVIS resource usage under system load. "
        "Observes CPU, RAM and battery, then automatically reduces background "
        "monitor priority, can pause the 3D avatar, lengthens proactive check "
        "intervals and limits concurrent heavy actions. "
        "Use when the PC is under load (gaming, video editing, low battery) "
        "or when the user asks to make JARVIS lighter / more aggressive / "
        "check current resource mode. "
        "Actions: status, auto (apply), set (mode=auto|performance|balanced|economy|manual), "
        "pause_avatar, resume_avatar, throttle (seconds=N)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "status | auto | set | pause_avatar | resume_avatar | throttle"
                ),
            },
            "mode": {
                "type": "STRING",
                "description": "For action=set: auto, performance, balanced, economy, manual",
            },
            "seconds": {
                "type": "NUMBER",
                "description": "For action=throttle: proactive interval in seconds (15-600)",
            },
        },
        "required": [],
    },
    "handler": resource_governor,
    "tier": "core",
}
