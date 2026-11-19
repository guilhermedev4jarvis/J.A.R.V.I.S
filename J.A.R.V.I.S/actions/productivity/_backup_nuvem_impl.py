
"""backup_nuvem — zip memory/ e envia ao Telegram; scheduler semanal."""
from __future__ import annotations
import os, threading, time, zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from core.outcome import done, failed
from actions.security._security_vision import audit, env, send_telegram, speak_short

_BASE = Path(__file__).resolve().parents[2]
_MEM = _BASE / "memory"
_TMP = _BASE / "memory" / "audit" / "backups"
_state: dict[str, Any] = {"thread": None, "stop": threading.Event()}

def _should_skip(path: Path) -> bool:
    # skip heavy old evidence
    try:
        if "evidencias" in path.parts or "gravacoes" in path.parts:
            age = time.time() - path.stat().st_mtime
            if age > 7 * 86400:
                return True
            if path.stat().st_size > 25 * 1024 * 1024:
                return True
    except Exception:
        pass
    return False

def do_backup() -> dict:
    _TMP.mkdir(parents=True, exist_ok=True)
    zpath = _TMP / f"memory_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    count = 0
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(_MEM):
            for name in files:
                fp = Path(root) / name
                if fp.resolve() == zpath.resolve():
                    continue
                if _should_skip(fp):
                    continue
                try:
                    zf.write(fp, arcname=str(fp.relative_to(_BASE)))
                    count += 1
                except Exception:
                    continue
    # Telegram sendDocument
    token, chat = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return {"ok": False, "reason": "telegram_not_configured", "zip": str(zpath), "files": count}
    try:
        import requests
        with open(zpath, "rb") as fh:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendDocument",
                data={"chat_id": chat, "caption": f"Backup memory/ ({count} arquivos)"},
                files={"document": fh},
                timeout=120,
            )
        ok = r.status_code == 200
        audit("backup_sent", tool="backup_nuvem", extra={"ok": ok, "files": count})
        return {"ok": ok, "files": count, "zip": str(zpath), "status_code": r.status_code}
    except Exception as e:
        audit("backup_fail", tool="backup_nuvem", extra={"error": str(e)[:140]})
        return {"ok": False, "reason": str(e)[:140], "zip": str(zpath)}

def _scheduler():
    last_day = None
    while not _state["stop"].is_set():
        try:
            now = datetime.now()
            # Sunday=6
            if now.weekday() == 6 and now.hour == 3 and now.minute < 5 and last_day != now.date():
                do_backup()
                last_day = now.date()
        except Exception as e:
            audit("backup_sched_err", tool="backup_nuvem", extra={"error": str(e)[:120]})
        _state["stop"].wait(60)

def start_scheduler() -> bool:
    if _state["thread"] and _state["thread"].is_alive():
        return True
    _state["stop"] = threading.Event()
    t = threading.Thread(target=_scheduler, daemon=True, name="backup-nuvem")
    _state["thread"] = t
    t.start()
    return True

def run(parameters=None, player=None, **_ctx) -> str:
    action = str((parameters or {}).get("action") or "now").lower()
    if action in ("now", "backup", "fazer"):
        r = do_backup()
        if r.get("ok"):
            speak_short("Backup enviado, Senhor.", player=player)
            return done("backup_nuvem", action="now", **r)
        return failed("backup_nuvem", r.get("reason", "backup_failed"), **{k: v for k, v in r.items() if k != "reason"})
    if action == "start_scheduler":
        return done("backup_nuvem", scheduler=start_scheduler())
    if action == "stop_scheduler":
        _state["stop"].set()
        return done("backup_nuvem", scheduler=False)
    return done("backup_nuvem", scheduler=bool(_state["thread"] and _state["thread"].is_alive()))
