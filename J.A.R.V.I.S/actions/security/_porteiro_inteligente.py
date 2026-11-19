"""Porteiro inteligente: veículo desconhecido parado, contexto entrega, Telegram inline."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_BASE = Path(__file__).resolve().parents[2]
_STATE_LOCK = threading.Lock()
_unknown_seen: dict[str, float] = {}  # plate -> first_seen_ts
_ignored_until: dict[str, float] = {}

try:
    from core.event_bus import publish as _eb_pub
except Exception:
    def _eb_pub(*_a, **_k):
        pass


def _is_night(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now()
    return now.hour >= 18 or now.hour < 6


def _delivery_context() -> str:
    bits = []
    for path in (
        _BASE / "memory" / "long_term.json",
        _BASE / "memory" / "graph.json",
    ):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        today = datetime.now().date().isoformat()
        for c in data.get("commitments") or []:
            if c.get("target_date") == today:
                bits.append(f"{c.get('entity')} {c.get('context')}")
        blob = json.dumps(data, ensure_ascii=False).lower()
        if any(w in blob for w in ("entrega", "delivery", "visita", "correios", "ifood", "mercado livre")):
            bits.append("menção a entrega/visita na memória")
    # email triage soft
    try:
        import actions.productivity.email_triage as email_triage
        r = str(email_triage.email_triage(parameters={"action": "scan", "query": "entrega visita"}))
        if "entrega" in r.lower() or "visita" in r.lower():
            bits.append("e-mail sugere entrega/visita")
    except Exception:
        pass
    return "; ".join(bits) if bits else "nenhuma entrega/visita explícita na memória"


def note_unknown_plate(plate: str, snapshot_path: Optional[str] = None) -> Optional[dict]:
    """Track unknown plates; if still present >15s emit waiting event + telegram."""
    plate = (plate or "").upper().strip()
    if not plate:
        return None
    now = time.time()
    with _STATE_LOCK:
        if plate in _ignored_until and now < _ignored_until[plate]:
            return {"ok": True, "ignored": True, "plate": plate}
        if plate not in _unknown_seen:
            _unknown_seen[plate] = now
            return {"ok": True, "tracking": True, "plate": plate, "duration_sec": 0}
        duration = now - _unknown_seen[plate]
        if duration < 15:
            return {"ok": True, "tracking": True, "plate": plate, "duration_sec": int(duration)}
        # fire once then reset timer to avoid spam
        _unknown_seen[plate] = now + 10_000  # park until ignore/clear
    ctx = _delivery_context()
    payload = {
        "plate": plate,
        "duration_sec": int(duration),
        "snapshot_path": snapshot_path,
        "expected_delivery_context": ctx,
    }
    _eb_pub("alpr.unknown_vehicle_waiting", **payload)
    send_porteiro_telegram(plate, snapshot_path, ctx, int(duration))
    return {"ok": True, "alerted": True, **payload}


def ignore_plate(plate: str, minutes: int = 15) -> None:
    plate = (plate or "").upper().strip()
    with _STATE_LOCK:
        _ignored_until[plate] = time.time() + minutes * 60
        _unknown_seen.pop(plate, None)


def clear_plate_track(plate: str) -> None:
    with _STATE_LOCK:
        _unknown_seen.pop((plate or "").upper().strip(), None)


def send_porteiro_telegram(plate: str, image_path: Optional[str], context: str, duration: int) -> dict:
    """Rich alert with inline keyboard (Telegram Bot API)."""
    import os
    import requests

    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        return {"ok": False, "reason": "telegram_not_configured"}
    text = (
        f"🚗 *Porteiro Inteligente*\n"
        f"Placa: `{plate}`\n"
        f"Parado há: *{duration}s*\n"
        f"Contexto: {context}"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🔓 Abrir Portão", "callback_data": f"porteiro:open:{plate}"},
                {"text": "🔊 Falar", "callback_data": f"porteiro:talk:{plate}"},
            ],
            [{"text": "🙈 Ignorar", "callback_data": f"porteiro:ignore:{plate}"}],
        ]
    }
    base = f"https://api.telegram.org/bot{token}"
    try:
        if image_path and Path(image_path).is_file():
            with open(image_path, "rb") as fh:
                r = requests.post(
                    f"{base}/sendPhoto",
                    data={"chat_id": chat, "caption": text[:1024], "parse_mode": "Markdown", "reply_markup": json.dumps(keyboard)},
                    files={"photo": fh},
                    timeout=(4, 20),
                )
        else:
            r = requests.post(
                f"{base}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "Markdown", "reply_markup": keyboard},
                timeout=(4, 12),
            )
        return {"ok": r.status_code == 200, "status": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def handle_callback(data: str, player=None) -> str:
    """Process callback_data porteiro:open|talk|ignore:PLATE."""
    parts = (data or "").split(":")
    if len(parts) < 3 or parts[0] != "porteiro":
        return "ignored"
    action, plate = parts[1], parts[2]
    if action == "ignore":
        ignore_plate(plate, 15)
        return f"Ignorado {plate} por 15 min"
    if action == "open":
        try:
            import actions.smarthome.smart_home as smart_home
            smart_home.smart_home(parameters={"action": "gate_open"})
        except Exception as e:
            return f"falha abrir: {e}"
        return f"Portão acionado para {plate}"
    if action == "talk":
        try:
            from ._security_vision import speak_short
            speak_short("Olá, por favor identifique-se. O morador foi notificado.", player=player, silent=False)
        except Exception:
            pass
        return f"TTS externo para {plate}"
    return "unknown"


def enrich_plate_event_night(payload: dict) -> dict:
    p = dict(payload or {})
    p["night"] = _is_night()
    return p
