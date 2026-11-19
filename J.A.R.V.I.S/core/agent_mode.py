"""
core/agent_mode.py — listen-only vs autonomous agent mode.

States
------
    listen      STT/TTS + memory + read-only tools. No desktop actuation,
                no destructive tools, no multi-step agents.
    assist      Default. Tools run with normal confirm gates.
    autonomous  Multi-step agents (desktop_agent, deep_research) may proceed
                without per-step banners; destructive actions still need confirm.

Persistence: config/agent_mode.json so a restart keeps the user's choice.
The UI should call set_mode() / get_mode() and show a clear indicator.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Literal

Mode = Literal["listen", "assist", "autonomous"]
_VALID = frozenset({"listen", "assist", "autonomous"})

_BASE = Path(__file__).resolve().parents[1]
_PATH = _BASE / "config" / "agent_mode.json"
_LOCK = threading.Lock()

_DEFAULT: dict[str, Any] = {
    "mode": "assist",
    "air_gapped": False,
    "strict_paths": False,
    "validate_feedback": True,  # show validate loop status on HUD
}

_state: dict[str, Any] = dict(_DEFAULT)
_loaded = False


def _load() -> None:
    global _state, _loaded
    if _loaded:
        return
    with _LOCK:
        if _loaded:
            return
        try:
            if _PATH.is_file():
                data = json.loads(_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    merged = dict(_DEFAULT)
                    merged.update({k: data[k] for k in _DEFAULT if k in data})
                    if merged["mode"] not in _VALID:
                        merged["mode"] = "assist"
                    _state = merged
        except Exception as e:
            print(f"[agent_mode] load failed: {e}")
        _loaded = True


def _save() -> None:
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(_state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception as e:
        print(f"[agent_mode] save failed: {e}")


def get_mode() -> Mode:
    _load()
    mode = _state.get("mode", "assist")
    return mode if mode in _VALID else "assist"  # type: ignore[return-value]


def set_mode(mode: str) -> Mode:
    """Set and persist mode. Invalid values fall back to assist."""
    _load()
    m = (mode or "").strip().lower()
    if m not in _VALID:
        m = "assist"
    with _LOCK:
        _state["mode"] = m
        _save()
    return m  # type: ignore[return-value]


def is_listen_only() -> bool:
    return get_mode() == "listen"


def is_autonomous() -> bool:
    return get_mode() == "autonomous"


def air_gapped() -> bool:
    _load()
    return bool(_state.get("air_gapped"))


def set_air_gapped(enabled: bool) -> None:
    _load()
    with _LOCK:
        _state["air_gapped"] = bool(enabled)
        _save()


def strict_paths() -> bool:
    _load()
    return bool(_state.get("strict_paths"))


def set_strict_paths(enabled: bool) -> None:
    _load()
    with _LOCK:
        _state["strict_paths"] = bool(enabled)
        _save()


def validate_feedback_enabled() -> bool:
    _load()
    return bool(_state.get("validate_feedback", True))


def set_validate_feedback(enabled: bool) -> None:
    _load()
    with _LOCK:
        _state["validate_feedback"] = bool(enabled)
        _save()


def snapshot() -> dict[str, Any]:
    _load()
    return dict(_state)


def tool_allowed(tool_name: str, risk: str = "review") -> tuple[bool, str]:
    """Return (allowed, reason) under the current mode + air-gap policy."""
    mode = get_mode()
    name = (tool_name or "").lower()

    if air_gapped():
        # Block anything that is clearly cloud-bound by name
        cloudish = (
            "web_search", "flight_finder", "youtube", "deep_research",
            "email_triage", "weather_report", "noticias", "cotacao",
        )
        if any(c in name for c in cloudish):
            return False, "air_gapped: cloud tool blocked"

    if mode == "listen":
        read_ok = risk == "safe" or name in {
            "recall_memory", "search_memory", "weather_report", "system_health",
            "network_status", "clipboard", "unit_convert", "timer", "battery",
        }
        # Still allow pure memory writes of notes? Conservative: no actuation.
        if name in {"save_memory", "remember", "forget", "undo"}:
            return True, "listen: memory ok"
        if not read_ok and risk in {"review", "destructive", "autonomous"}:
            return False, "listen_only: actuation blocked"
        if "desktop" in name or "computer_" in name or name in {
            "file_controller", "browser_control", "powershell_cmd",
            "send_message", "open_app",
        }:
            return False, "listen_only: actuation blocked"

    if mode == "assist" and risk == "autonomous":
        # Autonomous tools still run, but callers should prefer confirm_steps.
        return True, "assist: autonomous tools ok with caution"

    return True, f"mode={mode}"


def label_pt(mode: str | None = None) -> str:
    m = mode or get_mode()
    return {
        "listen": "somente escuta",
        "assist": "assistente",
        "autonomous": "autônomo",
    }.get(m, m)
