
"""modo_foco — minimiza apps de distração + timer TTS."""
from __future__ import annotations
import threading, time
from typing import Any
from core.outcome import done, ask
from actions.security._security_vision import audit, speak_short

_BLOCK = ("discord", "telegram", "whatsapp", "spotify", "steam", "tiktok", "instagram", "twitter", "chrome")
_state: dict[str, Any] = {"thread": None, "stop": threading.Event(), "until": None}

def _minimize():
    try:
        import pygetwindow as gw
        for w in gw.getAllWindows():
            title = (w.title or "").lower()
            if any(b in title for b in _BLOCK):
                try:
                    w.minimize()
                except Exception:
                    pass
    except Exception as e:
        audit("foco_min_fail", tool="modo_foco", extra={"error": str(e)[:100]})

def _timer(minutes: float, player=None):
    end = time.time() + max(1, minutes) * 60
    _state["until"] = end
    while not _state["stop"].is_set() and time.time() < end:
        time.sleep(1)
    if not _state["stop"].is_set():
        speak_short("Tempo de foco concluído, Senhor.", player=player)
        audit("foco_done", tool="modo_foco")
    _state["until"] = None

def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "start").lower()
    minutes = float(p.get("minutes") or p.get("value") or 25)
    if action in ("stop", "encerrar"):
        _state["stop"].set()
        speak_short("Modo foco encerrado, Senhor.", player=player)
        return done("modo_foco", action="stop", running=False)
    if action == "status":
        return done("modo_foco", running=bool(_state["thread"] and _state["thread"].is_alive()), until=_state.get("until"))
    _minimize()
    _state["stop"] = threading.Event()
    t = threading.Thread(target=_timer, args=(minutes, player), daemon=True, name="modo-foco")
    _state["thread"] = t
    t.start()
    speak_short(f"Modo foco por {int(minutes)} minutos, Senhor.", player=player)
    return done("modo_foco", action="start", minutes=minutes, running=True)
