
"""simulador_presenca — luzes/áudio aleatórios no período noturno."""
from __future__ import annotations
import random, threading, time
from datetime import datetime
from typing import Any
from core.outcome import done
from actions.security._security_vision import audit, speak_short

_state: dict[str, Any] = {"thread": None, "stop": threading.Event()}

def _in_window() -> bool:
    now = datetime.now().time()
    start = datetime.strptime("18:30", "%H:%M").time()
    end = datetime.strptime("23:30", "%H:%M").time()
    return start <= now <= end

def _loop(player=None):
    while not _state["stop"].is_set():
        try:
            if _in_window():
                try:
                    from .smart_home import smart_home
                    smart_home(parameters={"action": random.choice(["light_on", "light_off"])})
                except Exception as e:
                    audit("sim_light_fail", tool="simulador_presenca", extra={"error": str(e)[:100]})
                # soft tone optional
                try:
                    import numpy as np, sounddevice as sd
                    sr = 22050
                    t = np.linspace(0, 0.4, int(sr * 0.4), False)
                    wave = 0.05 * np.sin(2 * np.pi * 220 * t)
                    sd.play(wave.astype(np.float32), sr)
                    sd.wait()
                except Exception:
                    pass
                _state["stop"].wait(random.randint(120, 480))
            else:
                _state["stop"].wait(60)
        except Exception as e:
            audit("sim_loop_err", tool="simulador_presenca", extra={"error": str(e)[:120]})
            time.sleep(5)

def run(parameters=None, player=None, **_ctx) -> str:
    action = str((parameters or {}).get("action") or "status").lower()
    if action in ("start", "ativar", "viagem"):
        if _state["thread"] and _state["thread"].is_alive():
            return done("simulador_presenca", running=True, already=True)
        _state["stop"] = threading.Event()
        t = threading.Thread(target=_loop, args=(player,), daemon=True, name="sim-presenca")
        _state["thread"] = t
        t.start()
        speak_short("Simulador de presença ativo, Senhor.", player=player)
        return done("simulador_presenca", action="start", running=True)
    if action in ("stop", "desativar"):
        _state["stop"].set()
        if _state.get("thread"):
            _state["thread"].join(timeout=2)
        speak_short("Simulador de presença desligado, Senhor.", player=player)
        return done("simulador_presenca", action="stop", running=False)
    return done("simulador_presenca", running=bool(_state["thread"] and _state["thread"].is_alive()))
