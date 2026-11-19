
"""anti_sabotagem_energia — detecta desconexão da tomada via psutil."""
from __future__ import annotations
import threading, time
from typing import Any, Optional
from core.outcome import done
from ._security_vision import audit, env, send_telegram
try:
    from core.event_bus import publish as _eb_pub
except Exception:
    def _eb_pub(*a, **k): pass

_state: dict[str, Any] = {"thread": None, "stop": threading.Event(), "on_ac": None}

def _battery():
    try:
        import psutil
        return psutil.sensors_battery()
    except Exception:
        return None

def _loop():
    while not _state["stop"].is_set():
        try:
            b = _battery()
            if b is None:
                _state["stop"].wait(5)
                continue
            on_ac = bool(b.power_plugged)
            prev = _state.get("on_ac")
            pct = int(b.percent) if b.percent is not None else -1
            if prev is True and on_ac is False:
                msg = (
                    f"⚠️ *ALERTA DE ENERGIA*\nA energia foi cortada ou o carregador desconectado.\n"
                    f"Operando na bateria (*{pct}%*)."
                )
                send_telegram(msg, markdown=True)
                audit("power_unplugged", tool="anti_sabotagem_energia", extra={"pct": pct})
                _eb_pub("power.outage_detected", percent=pct)
            elif prev is False and on_ac is True:
                msg = f"✅ *Energia restaurada*\nTomada reconectada. Bateria em *{pct}%*."
                send_telegram(msg, markdown=True)
                audit("power_plugged", tool="anti_sabotagem_energia", extra={"pct": pct})
                _eb_pub("power.restored", percent=pct)
            _state["on_ac"] = on_ac
        except Exception as e:
            audit("power_monitor_err", tool="anti_sabotagem_energia", extra={"error": str(e)[:120]})
        _state["stop"].wait(3)

def start_monitor() -> bool:
    if _state["thread"] and _state["thread"].is_alive():
        return True
    _state["stop"] = threading.Event()
    t = threading.Thread(target=_loop, daemon=True, name="anti-sabotagem-energia")
    _state["thread"] = t
    t.start()
    return True

def stop_monitor() -> None:
    _state["stop"].set()
    if _state.get("thread"):
        _state["thread"].join(timeout=2)

def run(parameters=None, player=None, **_ctx) -> str:
    action = str((parameters or {}).get("action") or "status").lower()
    if action == "start":
        return done("anti_sabotagem_energia", running=start_monitor())
    if action == "stop":
        stop_monitor()
        return done("anti_sabotagem_energia", running=False)
    b = _battery()
    return done(
        "anti_sabotagem_energia",
        running=bool(_state["thread"] and _state["thread"].is_alive()),
        on_ac=None if not b else bool(b.power_plugged),
        percent=None if not b else b.percent,
    )
