"""Per-application volume/mute via pycaw on Windows; graceful fallback elsewhere."""
from __future__ import annotations

import platform
from typing import Optional

from core.outcome import ask, done, failed, unverified

_OS = platform.system()


def _sessions_windows() -> list[dict]:
    from pycaw.pycaw import AudioUtilities  # type: ignore
    out = []
    for s in AudioUtilities.GetAllSessions():
        if s.Process:
            try:
                vol = s.SimpleAudioVolume
                out.append({
                    "pid": s.Process.pid,
                    "name": s.Process.name(),
                    "muted": bool(vol.GetMute()),
                    "volume": round(float(vol.GetMasterVolume()) * 100),
                })
            except Exception:
                continue
    return out


def _set_windows(name: str, *, mute: Optional[bool] = None, volume: Optional[int] = None) -> tuple[int, str]:
    from pycaw.pycaw import AudioUtilities  # type: ignore
    target = name.lower().strip()
    hit = 0
    for s in AudioUtilities.GetAllSessions():
        if not s.Process:
            continue
        pname = (s.Process.name() or "").lower()
        if target not in pname and target not in pname.replace(".exe", ""):
            continue
        vol = s.SimpleAudioVolume
        if mute is not None:
            vol.SetMute(1 if mute else 0, None)
        if volume is not None:
            v = max(0, min(100, int(volume))) / 100.0
            vol.SetMasterVolume(v, None)
        hit += 1
    return hit, "ok" if hit else "no matching audio session"


def run(parameters: Optional[dict] = None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or p.get("mode") or "list").strip().lower()
    app = str(p.get("app") or p.get("process") or p.get("name") or "").strip()

    if _OS != "Windows":
        if action == "list":
            return unverified("app_audio_mixer", "per-app mixer requires Windows/pycaw on this OS")
        return failed("app_audio_mixer", "app_audio_mixer is Windows-only (pycaw)")

    try:
        if action in ("list", "show"):
            sessions = _sessions_windows()
            summary = ", ".join(f"{s['name']}:{s['volume']}%{' muted' if s['muted'] else ''}" for s in sessions[:20])
            return done("app_audio_mixer", op="list", count=len(sessions), sessions=summary or "(none)")

        if not app:
            return ask("app_audio_mixer", "Qual aplicativo? (ex: chrome, discord)")

        if action in ("mute",):
            n, msg = _set_windows(app, mute=True)
            return done("app_audio_mixer", op="mute", app=app, matched=n) if n else failed("app_audio_mixer", msg, app=app)

        if action in ("unmute",):
            n, msg = _set_windows(app, mute=False)
            return done("app_audio_mixer", op="unmute", app=app, matched=n) if n else failed("app_audio_mixer", msg, app=app)

        if action in ("volume", "set", "set_volume"):
            if p.get("volume") is None and p.get("level") is None:
                return ask("app_audio_mixer", "Qual volume de 0 a 100?")
            level = int(float(p.get("volume") if p.get("volume") is not None else p.get("level")))
            n, msg = _set_windows(app, volume=level)
            return done("app_audio_mixer", op="volume", app=app, volume=level, matched=n) if n else failed("app_audio_mixer", msg, app=app)

        return failed("app_audio_mixer", f"unknown action {action}")
    except ImportError:
        return failed("app_audio_mixer", "pycaw not installed — pip install pycaw comtypes")
    except Exception as e:
        return failed("app_audio_mixer", str(e))
