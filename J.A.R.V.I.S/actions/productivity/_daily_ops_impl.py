"""daily_ops — morning briefing, internet watchdog, visual object memory."""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.outcome import ask, done, failed

_BASE = Path(__file__).resolve().parents[2]
_OBJ = _BASE / "memory" / "objetos_vistos.json"
_lock = threading.Lock()
_wd = {"thread": None, "stop": threading.Event(), "online": None, "down_since": None}


def _env(k: str, d: str = "") -> str:
    return (os.getenv(k) or d or "").strip()


def _speak(text: str, player=None) -> None:
    if not text:
        return
    if player:
        for a in ("plugin_say", "say", "request_say"):
            fn = getattr(player, a, None)
            if callable(fn):
                try:
                    fn(text)
                    return
                except Exception:
                    pass
    try:
        from core import tts
        if hasattr(tts, "speak"):
            tts.speak(text)
    except Exception:
        pass


def _audit(kind: str, extra: Optional[dict] = None) -> None:
    try:
        from core import audit
        audit.log_event(kind, tool="daily_ops", extra=extra or {})
    except Exception:
        pass


def _net_ok(host: str = "1.1.1.1", port: int = 443, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _telegram(msg: str) -> None:
    token, chat = _env("TELEGRAM_BOT_TOKEN"), _env("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": msg[:4000]},
            timeout=10,
        )
    except Exception:
        pass


def _watchdog_loop() -> None:
    while not _wd["stop"].is_set():
        try:
            ok = _net_ok()
            prev = _wd.get("online")
            if prev is None:
                _wd["online"] = ok
            elif prev and not ok:
                _wd["down_since"] = time.time()
                _wd["online"] = False
                _audit("internet_down", {})
            elif (not prev) and ok:
                down = _wd.get("down_since")
                dur = int(time.time() - down) if down else 0
                _wd["online"] = True
                _wd["down_since"] = None
                msg = f"J.A.R.V.I.S.: internet restabelecida após ~{dur}s de indisponibilidade."
                _audit("internet_up", {"downtime_sec": dur})
                _telegram(msg)
            else:
                _wd["online"] = ok
        except Exception as e:
            print(f"[daily_ops] watchdog: {e}")
        _wd["stop"].wait(60)


def _briefing(player=None) -> str:
    parts = []
    # weather
    try:
        import actions.web_media.weather_report as weather_report
        w = weather_report.weather_report(
            parameters={"city": "São José do Rio Preto", "location": "São José do Rio Preto, SP"},
            player=player,
        )
        parts.append(f"Clima: {str(w)[:280]}")
    except Exception as e:
        parts.append(f"Clima indisponível ({e}).")
    # news
    try:
        import actions.web_media.noticias_brasil as noticias_brasil
        n = noticias_brasil.noticias_brasil(parameters={"limit": 3}, player=player)
        parts.append(f"Notícias: {str(n)[:320]}")
    except Exception as e:
        parts.append(f"Notícias indisponíveis ({e}).")
    # email / reminders
    try:
        from .email_triage import email_triage
        e = email_triage(parameters={"action": "summary"}, player=player)
        parts.append(f"E-mail: {str(e)[:220]}")
    except Exception:
        pass
    try:
        from .reminder import reminder
        r = reminder(parameters={"action": "list"}, player=player)
        parts.append(f"Lembretes: {str(r)[:220]}")
    except Exception:
        pass

    # Butler-style short spoken summary (details stay in outcome for Telegram/LLM)
    spoken = "Bom dia, Senhor. "
    # Prefer concise synthesis
    spoken += "Preparei o resumo de Rio Preto, notícias e pendências."
    try:
        from actions.security._security_vision import speak_short
        speak_short(spoken + " " + " ".join(parts)[:280], player=player)
    except Exception:
        _speak((spoken + " " + " ".join(parts))[:500], player=player)
    text = spoken + " " + " ".join(parts)
    _audit("briefing", {"chars": len(text)})
    try:
        from memory.cognitive_consolidate import consolidate, commitments_for_today
        consolidate()
        cms = commitments_for_today()
        if cms:
            bits = []
            for c in cms[:5]:
                bits.append(f"{c.get('entity')} — {c.get('context')} {c.get('hour') or ''}h")
            text = text + " Compromissos na memória: " + "; ".join(bits) + "."
    except Exception:
        pass
    try:
        from actions.finance_shopping._finance_audit import briefing_finance_snippet
        fin = briefing_finance_snippet()
        if fin:
            text = text + " " + fin
    except Exception:
        pass
    return done("daily_ops", action="briefing", summary=text[:1200])


def _load_objs() -> dict:
    if not _OBJ.is_file():
        return {"objects": {}}
    try:
        return json.loads(_OBJ.read_text(encoding="utf-8"))
    except Exception:
        return {"objects": {}}


def _save_objs(data: dict) -> None:
    with _lock:
        _OBJ.parent.mkdir(parents=True, exist_ok=True)
        _OBJ.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _webcam_png() -> Optional[bytes]:
    try:
        import cv2
        cam = cv2.VideoCapture(0)
        try:
            ok, frame = cam.read()
            if not ok:
                return None
            ok2, buf = cv2.imencode(".png", frame)
            return buf.tobytes() if ok2 else None
        finally:
            cam.release()
    except Exception:
        try:
            from actions.desktop.screenshot_ocr import _capture_png  # type: ignore
            return _capture_png()
        except Exception:
            return None


def _describe_object(png: bytes, obj: str) -> str:
    prompt = (
        f"Onde está o objeto '{obj}' nesta imagem? Descreva posição em português "
        "em 1-2 frases. Se não vir, diga que não encontrou."
    )
    try:
        from core import gemini as gem
        from google.genai import types as gtypes
        key = gem.api_key() if hasattr(gem, "api_key") else ""
        if key:
            part = gtypes.Part.from_bytes(data=png, mime_type="image/png")
            return (gem.text([prompt, part], timeout_ms=25_000, key=key) or "").strip()[:500]
    except Exception:
        pass
    return f"Não consegui analisar a imagem para localizar '{obj}'."


def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "").strip().lower()
    obj = str(p.get("object") or p.get("query") or "").strip()

    if not action:
        blob = " ".join(str(v) for v in p.values()).lower()
        if any(x in blob for x in ("bom dia", "resumo", "briefing")):
            action = "briefing"
        elif "memoriz" in blob:
            action = "memorize_object"
        elif "onde está" in blob or "onde esta" in blob:
            action = "find_object"
        elif "watchdog" in blob and "stop" in blob:
            action = "watchdog_stop"
        elif "watchdog" in blob:
            action = "watchdog_start"

    if action == "briefing":
        return _briefing(player=player)

    if action == "watchdog_start":
        with _lock:
            if _wd["thread"] and _wd["thread"].is_alive():
                return done("daily_ops", action="watchdog_start", already=True)
            _wd["stop"] = threading.Event()
            t = threading.Thread(target=_watchdog_loop, daemon=True, name="inet-watchdog")
            _wd["thread"] = t
            t.start()
        return done("daily_ops", action="watchdog_start", running=True)

    if action == "watchdog_stop":
        _wd["stop"].set()
        th = _wd.get("thread")
        if th:
            th.join(timeout=2)
        return done("daily_ops", action="watchdog_stop", running=False)

    if action == "watchdog_status":
        alive = bool(_wd["thread"] and _wd["thread"].is_alive())
        return done(
            "daily_ops",
            action="watchdog_status",
            running=alive,
            online=_wd.get("online"),
            down_since=_wd.get("down_since"),
        )

    if action == "memorize_object":
        if not obj:
            return ask("daily_ops", "Qual objeto devo memorizar?")
        png = _webcam_png()
        if not png:
            return failed("daily_ops", "não foi possível capturar imagem")
        desc = _describe_object(png, obj)
        data = _load_objs()
        data.setdefault("objects", {})[obj.lower()] = {
            "description": desc,
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
        _save_objs(data)
        _speak(desc, player=player)
        return done("daily_ops", action="memorize_object", object=obj, description=desc)

    if action == "find_object":
        if not obj:
            return ask("daily_ops", "Qual objeto você procura?")
        data = _load_objs()
        hit = (data.get("objects") or {}).get(obj.lower())
        if not hit:
            # try fresh look
            png = _webcam_png()
            if png:
                desc = _describe_object(png, obj)
                _speak(desc, player=player)
                return done("daily_ops", action="find_object", object=obj, description=desc, source="live")
            return failed("daily_ops", f"sem registro de '{obj}'")
        msg = f"{obj}: {hit.get('description')} (visto em {hit.get('ts')})"
        _speak(msg, player=player)
        return done("daily_ops", action="find_object", object=obj, **hit)

    return ask("daily_ops", "Briefing, watchdog de internet ou memória de objeto?")
