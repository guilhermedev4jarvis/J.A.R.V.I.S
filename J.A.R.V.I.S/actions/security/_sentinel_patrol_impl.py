"""sentinel_patrol — ronda / encomenda / ausente com captura thread-safe."""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

from core.outcome import ask, done
from ._security_vision import (
    run_perimeter_scan,
    simulate_invasion_scan,
    analyze_vision,
    audit,
    connect_icsee_and_capture,
    send_telegram,
    send_whatsapp,
    speak_short,
)

_INTERVAL = {"night": 15 * 60, "delivery": 10, "away": 30}
_state: dict[str, Any] = {
    "mode": None,
    "thread": None,
    "stop": threading.Event(),
    "last_png": None,
    "started_at": None,
}
_lock = threading.Lock()


def _motion(prev: bytes, cur: bytes) -> float:
    try:
        import cv2
        import numpy as np
        a = cv2.imdecode(np.frombuffer(prev, np.uint8), cv2.IMREAD_GRAYSCALE)
        b = cv2.imdecode(np.frombuffer(cur, np.uint8), cv2.IMREAD_GRAYSCALE)
        if a is None or b is None:
            return 0.0
        if a.shape != b.shape:
            b = cv2.resize(b, (a.shape[1], a.shape[0]))
        return float(cv2.absdiff(a, b).mean())
    except Exception as e:
        audit("sentinel_motion_fail", tool="sentinel_patrol", extra={"error": str(e)[:100]})
        return 0.0


def _loop(mode: str, player=None) -> None:
    interval = _INTERVAL.get(mode, 60)
    while not _state["stop"].is_set():
        try:
            cap = connect_icsee_and_capture(player=None, load_delay=2.0)
            if cap.get("ok") and cap.get("png"):
                png = cap["png"]
                path = cap.get("path")
                score = _motion(_state["last_png"], png) if _state.get("last_png") else 0.0
                _state["last_png"] = png
                vis = analyze_vision(png)
                low = vis.lower()
                person = any(w in low for w in ("pessoa", "homem", "mulher", "alguém", "alguem"))
                delivery = any(w in low for w in ("entreg", "moto", "pacote", "carteiro"))
                fire, msg, spoken = False, "", True
                if mode == "night" and (score > 12 or person):
                    fire, msg = True, f"Ronda noturna: possível presença. {vis}"
                elif mode == "delivery" and (delivery or person):
                    fire, msg = True, "Há alguém no portão da frente."
                    spoken = True
                elif mode == "away" and person:
                    fire, msg, spoken = True, f"Modo ausente: movimento humano. {vis}", False
                if fire:
                    if spoken:
                        speak_short(msg if mode == "delivery" else "Senhor, detectei movimento nas câmeras.", player=player)
                    send_telegram(msg, path, markdown=False)
                    send_whatsapp(msg, path, player=player)
                    audit("sentinel_alert", tool="sentinel_patrol", extra={"mode": mode})
        except Exception as e:
            audit("sentinel_loop_error", tool="sentinel_patrol", extra={"error": str(e)[:160]})
        _state["stop"].wait(interval)


def _start(mode: str, player=None) -> str:
    with _lock:
        if _state["thread"] and _state["thread"].is_alive():
            _state["stop"].set()
            _state["thread"].join(timeout=2)
        _state["stop"] = threading.Event()
        _state["mode"] = mode
        _state["started_at"] = time.time()
        _state["last_png"] = None
        t = threading.Thread(target=_loop, args=(mode, player), daemon=True, name=f"sentinel-{mode}")
        _state["thread"] = t
        t.start()
    phrases = {
        "night": "Ronda noturna ativa, Senhor. Avisarei se houver movimento.",
        "delivery": "Monitoramento do portão iniciado, Senhor. Avisarei assim que o entregador chegar.",
        "away": "",  # silent
    }
    speak_short(phrases.get(mode, ""), player=player, silent=(mode == "away"))
    audit("sentinel_start", tool="sentinel_patrol", extra={"mode": mode})
    return done("sentinel_patrol", action="start", mode=mode, interval_sec=_INTERVAL.get(mode))


def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or p.get("mode") or "").strip().lower()
    raw = " ".join(str(p.get(k) or "") for k in p).lower()
    if not action or action in ("start", "on"):
        if any(x in raw for x in ("encomenda", "entrega", "portão", "portao")):
            action = "start_delivery"
        elif any(x in raw for x in ("ausente", "viagem", "saindo")):
            action = "start_away"
        elif any(x in raw for x in ("noturn", "ronda", "sentinel")):
            action = "start_night"
        elif any(x in raw for x in ("simular", "invasor", "kaggle", "ucf")):
            action = "simular"
        elif any(x in raw for x in ("analisar", "perímetro", "perimetro", "suspeit", "câmeras", "cameras", "checar")):
            action = "analisar"
        elif "parar" in raw or "stop" in raw:
            action = "stop"
    if action in ("analisar", "analyze", "perimetro", "perimeter", "checar", "verificar"):
        result = run_perimeter_scan(player=player, announce=True, camera_profile="mixed")
        return done("sentinel_patrol", action="analisar", **{k: v for k, v in result.items() if k != "frames"})
    if action in ("simular", "simular_invasao", "simulate", "kaggle_test"):
        result = simulate_invasion_scan(player=player)
        if not result.get("ok"):
            return done("sentinel_patrol", action="simular", ok=False, reason=result.get("reason"))
        return done("sentinel_patrol", action="simular", **{k: v for k, v in result.items() if k != "frames"})
    if action == "status":
        alive = bool(_state["thread"] and _state["thread"].is_alive())
        return done("sentinel_patrol", action="status", mode=_state.get("mode"), running=alive)
    if action in ("stop", "parar"):
        _state["stop"].set()
        if _state.get("thread"):
            _state["thread"].join(timeout=3)
        _state["mode"] = None
        speak_short("Vigilância encerrada, Senhor.", player=player)
        return done("sentinel_patrol", action="stop", running=False)
    if action in ("start_night", "night", "ronda"):
        return _start("night", player)
    if action in ("start_delivery", "delivery", "encomenda"):
        return _start("delivery", player)
    if action in ("start_away", "away", "ausente"):
        return _start("away", player)
    return ask("sentinel_patrol", "Ronda noturna, portão ou modo ausente, Senhor?")
