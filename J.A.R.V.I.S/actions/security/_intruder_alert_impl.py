"""Absence guardian: watch for unknown face; lock + audit evidence."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.outcome import done, failed, started

_BASE = Path(__file__).resolve().parents[2]
_AUDIT = _BASE / "memory" / "audit"
_state = {"active": False, "stop": None}
_lock = threading.Lock()


def _audit(event: str, detail: dict) -> None:
    try:
        from core import audit
        audit.log_event(event, detail)
    except Exception:
        _AUDIT.mkdir(parents=True, exist_ok=True)
        path = _AUDIT / "intruder_events.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"event": event, **detail, "ts": time.time()}) + "\n")


def _capture_evidence() -> Optional[str]:
    try:
        from core import face_auth
        import cv2
        frame = face_auth.capture_from_camera()
        _AUDIT.mkdir(parents=True, exist_ok=True)
        dest = _AUDIT / f"intruder_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        cv2.imwrite(str(dest), frame)
        return str(dest)
    except Exception as e:
        print(f"[intruder] capture failed: {e}")
        return None


def _face_is_owner() -> bool:
    try:
        from core import face_auth
        score = face_auth.verify_from_camera()
        return bool(getattr(score, "accepted", False))
    except Exception:
        return False


def _lock_workstation() -> None:
    import platform
    if platform.system() == "Windows":
        try:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
        except Exception as e:
            print(f"[intruder] lock failed: {e}")
    else:
        import subprocess
        for cmd in (["loginctl", "lock-session"], ["gnome-screensaver-command", "-l"]):
            try:
                subprocess.run(cmd, timeout=5, capture_output=True)
                break
            except Exception:
                continue


def _watch_loop(poll: float, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            owner = _face_is_owner()
            if not owner:
                evidence = _capture_evidence()
                _audit("intruder_detected", {"evidence": evidence, "reason": "face_not_owner"})
                _lock_workstation()
                with _lock:
                    _state["active"] = False
                stop.set()
                return
        except Exception as e:
            print(f"[intruder] poll error: {e}")
        stop.wait(poll)


def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or p.get("mode") or "status").strip().lower()
    poll = float(p.get("poll_seconds") or 8.0)
    poll = max(3.0, min(poll, 60.0))

    if action in ("status",):
        return done("intruder_alert", active=bool(_state.get("active")))

    if action in ("start", "arm", "enable", "watch"):
        with _lock:
            if _state.get("active"):
                return done("intruder_alert", op="start", active=True, note="already armed")
            stop = threading.Event()
            _state["stop"] = stop
            _state["active"] = True
        t = threading.Thread(target=_watch_loop, args=(poll, stop), daemon=True, name="intruder-watch")
        t.start()
        _audit("intruder_armed", {"poll": poll})
        return started("intruder_alert", op="start", poll_seconds=poll)

    if action in ("stop", "disarm", "disable"):
        with _lock:
            stop = _state.get("stop")
            if stop:
                stop.set()
            _state["active"] = False
            _state["stop"] = None
        _audit("intruder_disarmed", {})
        return done("intruder_alert", op="stop", active=False)

    if action in ("test_lock",):
        _lock_workstation()
        return done("intruder_alert", op="test_lock")

    return failed("intruder_alert", f"unknown action {action}. Use start|stop|status")
