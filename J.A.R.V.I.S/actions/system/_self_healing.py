"""Self-healing 24/7: RTSP, Ollama, Telegram polling."""
from __future__ import annotations

import os
import subprocess
import threading
import time
from typing import Any, Optional

_state: dict[str, Any] = {
    "thread": None,
    "stop": threading.Event(),
    "fails": {"rtsp": 0, "ollama": 0, "telegram": 0},
}

try:
    from core.event_bus import publish as _eb_pub
except Exception:
    def _eb_pub(*_a, **_k):
        pass


def _audit(kind: str, extra: dict) -> None:
    try:
        from core import audit as a
        a.log_event(kind, tool="self_healing", extra=extra)
    except Exception:
        pass


def check_rtsp() -> dict:
    url = (os.getenv("ICSEE_RTSP_URL") or "").strip()
    if not url:
        return {"ok": True, "skipped": True}
    try:
        import cv2
        cap = cv2.VideoCapture(url)
        try:
            ok, frame = cap.read()
            if ok and frame is not None:
                _state["fails"]["rtsp"] = 0
                return {"ok": True}
        finally:
            cap.release()
        raise RuntimeError("empty_frame")
    except Exception as e:
        _state["fails"]["rtsp"] = int(_state["fails"].get("rtsp") or 0) + 1
        # reconnect attempt with backoff
        time.sleep(min(8, 0.5 * (2 ** min(4, _state["fails"]["rtsp"]))))
        try:
            import cv2
            cap = cv2.VideoCapture(url)
            try:
                ok, frame = cap.read()
                healed = bool(ok and frame is not None)
            finally:
                cap.release()
        except Exception:
            healed = False
        if healed:
            _state["fails"]["rtsp"] = 0
            _eb_pub("system.service_healed", service="rtsp")
            _audit("service_healed", {"service": "rtsp"})
            return {"ok": True, "healed": True}
        return {"ok": False, "error": str(e)[:120], "fails": _state["fails"]["rtsp"]}


def check_ollama() -> dict:
    try:
        from core.resilience import http_request
        r = http_request("GET", "http://127.0.0.1:11434/api/tags", timeout=(2, 4), attempts=1, offline_result=None)
        if r is not None and getattr(r, "status_code", 0) == 200:
            _state["fails"]["ollama"] = 0
            return {"ok": True}
        raise RuntimeError("bad_status")
    except Exception as e:
        _state["fails"]["ollama"] = int(_state["fails"].get("ollama") or 0) + 1
        # try restart
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(2)
            _eb_pub("system.service_healed", service="ollama")
            _audit("service_healed", {"service": "ollama"})
            return {"ok": True, "healed": True, "error": str(e)[:80]}
        except Exception as e2:
            return {"ok": False, "error": str(e2)[:120], "fails": _state["fails"]["ollama"]}


def check_telegram() -> dict:
    try:
        from actions.web_media._telegram_commander_impl import _state as tg_state, start_listener
        alive = bool(tg_state.get("thread") and tg_state["thread"].is_alive())
        if alive:
            _state["fails"]["telegram"] = 0
            return {"ok": True, "running": True}
        _state["fails"]["telegram"] = int(_state["fails"].get("telegram") or 0) + 1
        start_listener(player=tg_state.get("player"))
        _eb_pub("system.service_healed", service="telegram")
        _audit("service_healed", {"service": "telegram"})
        return {"ok": True, "healed": True}
    except Exception as e:
        _state["fails"]["telegram"] = int(_state["fails"].get("telegram") or 0) + 1
        return {"ok": False, "error": str(e)[:120], "fails": _state["fails"]["telegram"]}


def _notify_persistent_failure(service: str, fails: int) -> None:
    if fails < 3:
        return
    try:
        from actions.security._security_vision import send_telegram
        send_telegram(f"⚠️ Self-healing: *{service}* falhou {fails}x consecutivas.", markdown=True)
    except Exception:
        pass


def _loop():
    while not _state["stop"].is_set():
        try:
            for name, fn in (("rtsp", check_rtsp), ("ollama", check_ollama), ("telegram", check_telegram)):
                try:
                    r = fn()
                    if not r.get("ok") and not r.get("skipped"):
                        _notify_persistent_failure(name, int(_state["fails"].get(name) or 0))
                except Exception as e:
                    _audit("self_heal_err", {"service": name, "error": str(e)[:120]})
        except Exception as e:
            _audit("self_heal_loop_err", {"error": str(e)[:120]})
        _state["stop"].wait(60)


def start_watchdog() -> bool:
    if _state["thread"] and _state["thread"].is_alive():
        return True
    _state["stop"] = threading.Event()
    t = threading.Thread(target=_loop, daemon=True, name="self-healing")
    _state["thread"] = t
    t.start()
    return True


def stop_watchdog() -> None:
    _state["stop"].set()


def status() -> dict:
    return {
        "running": bool(_state["thread"] and _state["thread"].is_alive()),
        "fails": dict(_state["fails"]),
    }
