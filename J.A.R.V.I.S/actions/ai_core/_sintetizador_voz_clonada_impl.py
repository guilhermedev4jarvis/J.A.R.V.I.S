"""Gerenciador de perfis prosodicos TTS integrado ao core/echo."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from core.outcome import done

_BASE = Path(__file__).resolve().parents[2]
_PROFILE_STATE = _BASE / "memory" / "voice_profile.json"

PROFILES: Dict[str, Dict[str, Any]] = {
    "padrao": {"rate": 1.0, "pitch": 0.0, "volume": 0.9},
    "alerta_critico": {"rate": 1.18, "pitch": 2.0, "volume": 1.0},
    "briefing_matinal": {"rate": 1.06, "pitch": 0.5, "volume": 0.92},
    "tutor_calmo": {"rate": 0.92, "pitch": -0.5, "volume": 0.85},
    "modo_noturno_sussurro": {"rate": 0.88, "pitch": -1.5, "volume": 0.45},
}


def _save_active(profile: str) -> Dict[str, Any]:
    cfg = {"active_profile": profile, "params": PROFILES.get(profile, PROFILES["padrao"])}
    _PROFILE_STATE.parent.mkdir(parents=True, exist_ok=True)
    _PROFILE_STATE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def _get_active() -> Dict[str, Any]:
    if _PROFILE_STATE.exists():
        try:
            return json.loads(_PROFILE_STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"active_profile": "padrao", "params": PROFILES["padrao"]}


def run(parameters=None, player=None, session_memory=None, **ctx):
    params = parameters or {}
    action = str(params.get("action") or "status").lower()
    profile = str(params.get("profile") or "padrao").lower()
    text = str(params.get("text") or "").strip()

    if profile not in PROFILES:
        profile = "padrao"

    if action == "set_profile":
        cfg = _save_active(profile)
        return done("sintetizador_voz_clonada", f"Perfil de voz alterado para '{profile}'.", cfg)

    if action == "speak":
        cfg = _save_active(profile) if "profile" in params else _get_active()
        spoken = False
        if text:
            try:
                from core import echo
                if hasattr(echo, "speak"):
                    echo.speak(text)
                    spoken = True
            except Exception:
                pass
        return done("sintetizador_voz_clonada", "Sintese de voz processada.", {"spoken": spoken, "text": text, **cfg})

    return done("sintetizador_voz_clonada", "Perfil de voz atual.", {**_get_active(), "available": list(PROFILES.keys())})