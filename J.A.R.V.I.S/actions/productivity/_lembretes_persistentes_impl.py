
"""lembretes_persistentes — JSON + scheduler daemon."""
from __future__ import annotations
import json, threading, time
from datetime import datetime
from pathlib import Path
from typing import Any
from core.outcome import done, ask
from actions.security._security_vision import audit, send_telegram, speak_short

_PATH = Path(__file__).resolve().parents[2] / "memory" / "lembretes.json"
_lock = threading.Lock()
_state: dict[str, Any] = {"thread": None, "stop": threading.Event()}

def _load():
    if not _PATH.is_file():
        return {"items": []}
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"items": []}

def _save(data):
    with _lock:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _loop(player=None):
    while not _state["stop"].is_set():
        try:
            data = _load()
            now = datetime.now().strftime("%H:%M")
            changed = False
            for it in data.get("items") or []:
                if it.get("done"):
                    continue
                if it.get("time") == now:
                    last = it.get("last_nudge")
                    if last != now:  # first nudge this minute
                        it["last_nudge"] = now
                        it["nudge_count"] = int(it.get("nudge_count") or 0) + 1
                        msg = f"Lembrete, Senhor: {it.get('text')}"
                        speak_short(msg, player=player)
                        send_telegram(f"⏰ *Lembrete*\n{it.get('text')}", markdown=True)
                        changed = True
                    elif int(it.get("nudge_count") or 0) > 0:
                        # every 5 minutes while same hour-minute window is tricky; use timestamp
                        pass
                # repeat every 5 min if pending and last_alert older than 5 min
                la = it.get("last_alert_ts") or 0
                if it.get("time") <= now and (time.time() - float(la)) >= 300 and not it.get("done"):
                    # only if reminder time already passed today roughly
                    if it.get("time") == now or (it.get("nudge_count") or 0) > 0:
                        it["last_alert_ts"] = time.time()
                        it["nudge_count"] = int(it.get("nudge_count") or 0) + 1
                        speak_short(f"Ainda pendente, Senhor: {it.get('text')}", player=player)
                        send_telegram(f"⏰ Lembrete pendente: {it.get('text')}")
                        changed = True
            if changed:
                _save(data)
        except Exception as e:
            audit("lembrete_loop_err", tool="lembretes_persistentes", extra={"error": str(e)[:120]})
        _state["stop"].wait(30)

def start_scheduler(player=None) -> bool:
    if _state["thread"] and _state["thread"].is_alive():
        return True
    _state["stop"] = threading.Event()
    t = threading.Thread(target=_loop, args=(player,), daemon=True, name="lembretes")
    _state["thread"] = t
    t.start()
    return True

def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "list").lower()
    if action in ("start_scheduler", "start"):
        return done("lembretes_persistentes", scheduler=start_scheduler(player))
    if action == "stop_scheduler":
        _state["stop"].set()
        return done("lembretes_persistentes", scheduler=False)
    if action in ("add", "lembrar"):
        text = str(p.get("text") or p.get("item") or "").strip()
        tm = str(p.get("time") or "").strip()
        if not text or not tm:
            return ask("lembretes_persistentes", "Informe a tarefa e o horário HH:MM, Senhor.")
        data = _load()
        data.setdefault("items", []).append({"text": text, "time": tm, "done": False})
        _save(data)
        speak_short(f"Lembrete às {tm} anotado, Senhor.", player=player)
        return done("lembretes_persistentes", action="add", text=text, time=tm)
    if action in ("confirm", "confirmar"):
        data = _load()
        for it in data.get("items") or []:
            if not it.get("done"):
                it["done"] = True
                break
        _save(data)
        speak_short("Lembrete confirmado, Senhor.", player=player)
        return done("lembretes_persistentes", action="confirm")
    data = _load()
    return done("lembretes_persistentes", action="list", items=data.get("items") or [],
                scheduler=bool(_state["thread"] and _state["thread"].is_alive()))
