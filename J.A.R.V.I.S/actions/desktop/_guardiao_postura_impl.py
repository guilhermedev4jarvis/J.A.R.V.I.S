
"""guardiao_postura — webcam periódica + visão + privacidade."""
from __future__ import annotations
import threading, time
from pathlib import Path
from typing import Any
from core.outcome import done
from actions.security._security_vision import audit, speak_short

_state: dict[str, Any] = {"thread": None, "stop": threading.Event()}
_INTERVAL = 25 * 60

def _frame_bytes():
    try:
        import cv2
        cam = cv2.VideoCapture(0)
        try:
            ok, frame = cam.read()
            if not ok:
                return None
            ok2, buf = cv2.imencode(".jpg", frame)
            return buf.tobytes() if ok2 else None
        finally:
            cam.release()
    except Exception as e:
        audit("postura_cam_fail", tool="guardiao_postura", extra={"error": str(e)[:100]})
        return None

def _assess(jpg: bytes) -> str:
    try:
        from core import gemini as gem
        from google.genai import types as gtypes
        key = gem.api_key() if hasattr(gem, "api_key") else ""
        if key:
            part = gtypes.Part.from_bytes(data=jpg, mime_type="image/jpeg")
            return (gem.text([
                "Avalie postura ergonomia em 1 frase: curvado? fadiga? Só orientação, sem identificar pessoa.",
                part,
            ], timeout_ms=20000, key=key) or "").strip()[:240]
    except Exception:
        pass
    return "Lembrete ergonômico genérico."

def _loop(player=None):
    while not _state["stop"].is_set():
        tmp = None
        try:
            data = _frame_bytes()
            if data:
                tmp = Path(__file__).resolve().parents[2] / "memory" / "tmp_postura.jpg"
                tmp.write_bytes(data)
                note = _assess(data)
                low = note.lower()
                if any(w in low for w in ("curv", "inclin", "fadiga", "ombros", "pescoço", "pescoco")):
                    speak_short("Senhor, ajuste a postura e beba um pouco de água.", player=player)
                else:
                    speak_short("Pausa ergonômica, Senhor. Hidrate-se.", player=player)
        except Exception as e:
            audit("postura_loop_err", tool="guardiao_postura", extra={"error": str(e)[:120]})
        finally:
            try:
                if tmp and tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
        _state["stop"].wait(_INTERVAL)

def run(parameters=None, player=None, **_ctx) -> str:
    action = str((parameters or {}).get("action") or "status").lower()
    if action in ("start", "ativar"):
        if _state["thread"] and _state["thread"].is_alive():
            return done("guardiao_postura", running=True, already=True)
        _state["stop"] = threading.Event()
        t = threading.Thread(target=_loop, args=(player,), daemon=True, name="guardiao-postura")
        _state["thread"] = t
        t.start()
        speak_short("Monitor de postura ativo, Senhor.", player=player)
        return done("guardiao_postura", action="start", running=True)
    if action in ("stop", "desativar"):
        _state["stop"].set()
        speak_short("Monitor de postura desligado, Senhor.", player=player)
        return done("guardiao_postura", action="stop", running=False)
    return done("guardiao_postura", running=bool(_state["thread"] and _state["thread"].is_alive()))
