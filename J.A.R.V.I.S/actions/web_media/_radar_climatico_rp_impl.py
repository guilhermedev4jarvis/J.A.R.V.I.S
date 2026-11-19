
"""radar_climatico_rp — Open-Meteo short-term storm alerts for Rio Preto."""
from __future__ import annotations
import threading, time
from typing import Any
from core.outcome import done
from actions.security._security_vision import audit, send_telegram, speak_short
try:
    from core.event_bus import publish as _eb_pub
except Exception:
    def _eb_pub(*a, **k): pass

LAT, LON = -20.8113, -49.3758
_state: dict[str, Any] = {"thread": None, "stop": threading.Event(), "last": None}

def _forecast() -> dict:
    try:
        from core.resilience import http_request
    except Exception:
        http_request = None
    import requests
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&hourly=precipitation,precipitation_probability,weathercode,windgusts_10m"
        "&forecast_hours=2&timezone=America%2FSao_Paulo"
    )
    if http_request:
        r = http_request('GET', url, timeout=(4, 10), attempts=3, offline_result=None)
    else:
        r = requests.get(url, timeout=(4, 10))
    if r is None:
        raise RuntimeError('offline')
    r.raise_for_status()
    return r.json()

def _assess(data: dict) -> dict:
    hourly = data.get("hourly") or {}
    precip = hourly.get("precipitation") or []
    prob = hourly.get("precipitation_probability") or []
    gust = hourly.get("windgusts_10m") or []
    codes = hourly.get("weathercode") or []
    max_p = max(precip[:3] or [0])
    max_prob = max(prob[:3] or [0])
    max_g = max(gust[:3] or [0])
    # WMO: 80-99 = showers/thunderstorm
    storm = any(int(c) >= 80 for c in codes[:3] if c is not None)
    alert = storm or max_p >= 2.0 or max_prob >= 70 or max_g >= 60
    return {
        "alert": alert,
        "storm": storm,
        "max_precip_mm": max_p,
        "max_prob": max_prob,
        "max_gust": max_g,
        "city": "São José do Rio Preto - SP",
    }

def check_and_notify(player=None, *, force_voice: bool = False) -> dict:
    try:
        data = _forecast()
        info = _assess(data)
        _state["last"] = info
        if info.get("alert"):
            msg = (
                "Senhor, há previsão de chuva forte em Rio Preto nos próximos minutos. "
                "Recomendo recolher roupas do varal e fechar as janelas."
            )
            speak_short(msg, player=player)
            send_telegram(
                f"*Radar climático — Rio Preto*\nAlerta ativo. "
                f"Precip≈{info['max_precip_mm']}mm · Prob={info['max_prob']}% · Rajadas={info['max_gust']}km/h",
                markdown=True,
            )
            audit("clima_alert", tool="radar_climatico_rp", extra=info)
            _eb_pub("weather.storm_alert", **{k: info.get(k) for k in ("max_precip_mm","max_prob","max_gust","city","storm")})
        elif force_voice:
            speak_short("Sem alerta de tempestade nas próximas duas horas em Rio Preto, Senhor.", player=player)
        return {"ok": True, **info}
    except Exception as e:
        audit("clima_fail", tool="radar_climatico_rp", extra={"error": str(e)[:140]})
        return {"ok": False, "reason": "rede_indisponivel", "detail": str(e)[:160], "offline": True}

def _loop(player=None):
    while not _state["stop"].is_set():
        try:
            check_and_notify(player=player, force_voice=False)
        except Exception as e:
            audit("clima_loop_err", tool="radar_climatico_rp", extra={"error": str(e)[:120]})
        _state["stop"].wait(45 * 60)

def start_monitor(player=None) -> bool:
    if _state["thread"] and _state["thread"].is_alive():
        return True
    _state["stop"] = threading.Event()
    t = threading.Thread(target=_loop, args=(player,), daemon=True, name="radar-climatico-rp")
    _state["thread"] = t
    t.start()
    return True

def run(parameters=None, player=None, **_ctx) -> str:
    action = str((parameters or {}).get("action") or "check_now").lower()
    if action in ("start", "ativar"):
        start_monitor(player)
        speak_short("Radar climático de Rio Preto ativado, Senhor.", player=player)
        return done("radar_climatico_rp", action="start", running=True)
    if action in ("stop", "desativar"):
        _state["stop"].set()
        return done("radar_climatico_rp", action="stop", running=False)
    if action == "status":
        return done(
            "radar_climatico_rp",
            running=bool(_state["thread"] and _state["thread"].is_alive()),
            last=_state.get("last"),
        )
    r = check_and_notify(player=player, force_voice=True)
    return done("radar_climatico_rp", action="check_now", **r)
