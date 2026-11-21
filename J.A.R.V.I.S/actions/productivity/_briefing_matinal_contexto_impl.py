"""Consolidador de briefing matinal contextual."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from core.outcome import done


def _safe_call(fn, *args, **kwargs) -> str:
    try:
        res = fn(*args, **kwargs)
        if isinstance(res, dict):
            return str(res.get("message") or res.get("summary") or "")
        return str(res or "")
    except Exception:
        return ""


def run(parameters=None, player=None, session_memory=None, **ctx):
    params = parameters or {}
    should_speak = bool(params.get("speak", False))

    weather_txt = ""
    try:
        from actions.web_media import _radar_climatico_rp_impl as rc
        if hasattr(rc, "run"):
            weather_txt = _safe_call(rc.run, {})
    except Exception:
        pass

    reminders_txt = ""
    try:
        from actions.productivity import _lembretes_persistentes_impl as lp
        if hasattr(lp, "run"):
            reminders_txt = _safe_call(lp.run, {"action": "list"})
    except Exception:
        pass

    parts = [f"Bom dia. Hoje e {datetime.now().strftime('%d/%m/%Y')}."]
    if weather_txt:
        parts.append(f"Clima: {weather_txt}")
    if reminders_txt:
        parts.append(f"Lembretes: {reminders_txt}")
    if len(parts) == 1:
        parts.append("Nenhum alerta critico pendente para esta manha.")

    script = " ".join(parts)
    if should_speak:
        try:
            from core import echo
            if hasattr(echo, "speak"):
                echo.speak(script)
        except Exception:
            pass

    payload: Dict[str, Any] = {"script": script, "spoken": should_speak}
    return done("briefing_matinal_contexto", script, payload)