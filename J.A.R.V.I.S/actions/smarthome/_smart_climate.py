"""Pré-climatização contextual (ALPR + clima + pré-sono)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

_BASE = Path(__file__).resolve().parents[2]
_CFG = _BASE / "config" / "smart_climate.json"

try:
    from core.event_bus import publish as _eb_pub
except Exception:
    def _eb_pub(*_a, **_k):
        pass


def _cfg() -> dict:
    try:
        return json.loads(_CFG.read_text(encoding="utf-8"))
    except Exception:
        return {
            "hot_threshold_c": 27,
            "cold_threshold_c": 16,
            "sleep_hour": 22,
            "sleep_minute": 30,
            "pre_sleep_minutes": 20,
            "trusted_plates": ["FIK5J12"],
        }


def _temp_c() -> Optional[float]:
    try:
        from actions.web_media._radar_climatico_rp_impl import _forecast
        data = _forecast()
        # open-meteo style
        cur = (data or {}).get("current") or {}
        if "temperature_2m" in cur:
            return float(cur["temperature_2m"])
        hourly = (data or {}).get("hourly") or {}
        temps = hourly.get("temperature_2m") or []
        if temps:
            return float(temps[0])
    except Exception:
        pass
    return None


def _activate_climate(reason: str, temp: Optional[float]) -> dict:
    cfg = _cfg()
    mode = "cool"
    target = float(cfg.get("target_cool_temp_c") or 23)
    if temp is not None:
        if temp >= float(cfg.get("hot_threshold_c") or 27):
            mode = "cool"
            target = float(cfg.get("target_cool_temp_c") or 23)
        elif temp <= float(cfg.get("cold_threshold_c") or 16):
            mode = "heat"
            target = float(cfg.get("target_heat_temp_c") or 24)
    provider = str(cfg.get("default_provider") or "generic").lower()
    alias = str(cfg.get("device_alias") or "ar_quarto")
    result = {"ok": True, "provider": provider}
    if False:  # vendor-specific providers removed
        try:
            result = control("turn_on", alias=alias, temperature=target, mode=mode)
        except Exception as e:
            result = {"ok": False, "error": str(e)[:160]}
    else:
        try:
            from .smart_home import smart_home
            smart_home(parameters={"action": "climate_on", "mode": mode, "temperature": target})
        except Exception:
            pass
    try:
        from actions.security._security_vision import audit
        audit("smart_climate", extra={"reason": reason, "temp": temp, "mode": mode, "target": target, "provider": provider})
    except Exception:
        pass
    _eb_pub("climate.precondition", reason=reason, temp=temp, mode=mode, target=target, provider=provider)
    return {"ok": bool(result.get("ok", True)), "reason": reason, "temp": temp, "mode": mode, "target": target, "provider": provider, "driver": result}


def on_trusted_vehicle_arrival(plate: str, is_known: bool = True) -> Optional[dict]:
    cfg = _cfg()
    plates = [str(p).upper() for p in (cfg.get("trusted_plates") or ["FIK5J12"])]
    if not is_known or plate.upper() not in plates:
        return None
    temp = _temp_c()
    if temp is None:
        return {"ok": False, "reason": "no_temp"}
    hot = float(cfg.get("hot_threshold_c") or 27)
    cold = float(cfg.get("cold_threshold_c") or 16)
    if temp > hot or temp < cold:
        return _activate_climate(f"alpr_arrival:{plate}", temp)
    return {"ok": True, "skipped": True, "temp": temp, "reason": "within_range"}


def check_pre_sleep(someone_home: bool = True) -> Optional[dict]:
    if not someone_home:
        return None
    cfg = _cfg()
    now = datetime.now()
    sleep_at = now.replace(
        hour=int(cfg.get("sleep_hour") or 22),
        minute=int(cfg.get("sleep_minute") or 30),
        second=0,
        microsecond=0,
    )
    window_start = sleep_at - timedelta(minutes=int(cfg.get("pre_sleep_minutes") or 20))
    if not (window_start <= now <= sleep_at):
        return {"ok": True, "skipped": True, "reason": "outside_pre_sleep_window"}
    temp = _temp_c()
    if temp is None:
        return {"ok": False, "reason": "no_temp"}
    ideal_min = float(cfg.get("ideal_min_c") or 20)
    ideal_max = float(cfg.get("ideal_max_c") or 24)
    if temp < ideal_min or temp > ideal_max:
        return _activate_climate("pre_sleep", temp)
    return {"ok": True, "skipped": True, "temp": temp}


_last_schedule_fire: dict[str, str] = {}


def run_due_schedules(now: Optional[datetime] = None) -> list[dict]:
    """Run enabled schedules once per minute (idempotent)."""
    cfg = _cfg()
    now = now or datetime.now()
    hhmm = now.strftime("%H:%M")
    fired = []
    for sch in cfg.get("schedules") or []:
        if not sch.get("enabled", True):
            continue
        if str(sch.get("time") or "") != hhmm:
            continue
        name = str(sch.get("name") or hhmm)
        key = f"{name}:{hhmm}:{now.date().isoformat()}"
        if _last_schedule_fire.get(name) == key:
            continue
        _last_schedule_fire[name] = key
        action = str(sch.get("action") or "turn_on").lower()
        alias = str(cfg.get("device_alias") or "ar_quarto")
        mode = sch.get("mode") or "cool"
        target = sch.get("target_temp_c")
        try:
            if action in ("turn_on", "on", "ligar"):
                r = control("turn_on", alias=alias, temperature=float(target or cfg.get("target_cool_temp_c") or 23), mode=str(mode))
            elif action in ("turn_off", "off", "desligar"):
                r = control("turn_off", alias=alias)
            else:
                r = control(action, alias=alias, temperature=float(target) if target is not None else None, mode=str(mode) if mode else None)
        except Exception as e:
            r = {"ok": False, "error": str(e)[:160]}
        entry = {"schedule": name, "time": hhmm, "result": r}
        fired.append(entry)
        _eb_pub("climate.schedule_fired", schedule=name, time=hhmm, action=action)
    return fired


def climate_power(on: bool, params=None):
    """Generic climate power toggle via webhook_bridge / event bus (no vendor lock-in)."""
    params = dict(params or {})
    params["power"] = bool(on)
    try:
        from core.event_bus import EventBus
        EventBus.get().publish("climate.power", {"on": on, **{k: params[k] for k in params if k != "power"}})
    except Exception:
        pass
    return {"ok": True, "power": on, "provider": "generic"}


def climate_status(params=None):
    params = dict(params or {})
    return {"ok": True, "provider": "generic", "message": "Status via provider genérico (webhook/HA/MQTT)."}
