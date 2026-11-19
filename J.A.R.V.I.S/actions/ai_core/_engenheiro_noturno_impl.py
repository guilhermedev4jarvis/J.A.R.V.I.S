
"""engenheiro_noturno — manutenção automatizada de madrugada."""
from __future__ import annotations
import subprocess, sys, threading, time
from datetime import datetime
from pathlib import Path
from typing import Any
from core.outcome import done
from actions.security._security_vision import audit, cleanup_old_evidence, send_telegram, speak_short

_BASE = Path(__file__).resolve().parents[2]
_state: dict[str, Any] = {"thread": None, "stop": threading.Event()}

def run_diagnostic() -> dict:
    report = {"ts": datetime.now().isoformat(timespec="seconds"), "pytest": None, "deps": None, "cleanup": None}
    # pytest
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/"],
            cwd=str(_BASE),
            capture_output=True,
            text=True,
            timeout=300,
        )
        report["pytest"] = {"code": r.returncode, "out": ((r.stdout or "") + (r.stderr or ""))[-1500:]}
    except Exception as e:
        report["pytest"] = {"error": str(e)[:200]}
    # deps
    try:
        import actions.system.dependency_health as dependency_health
        report["deps"] = str(dependency_health.dependency_health(parameters={"action": "check"}))[:800]
    except Exception as e:
        report["deps"] = f"error:{e}"
    # cleanup evidence + tmp
    try:
        report["cleanup"] = cleanup_old_evidence(7)
        tmp = _BASE / "memory"
        for p in tmp.glob("tmp_*"):
            try:
                if p.is_file() and time.time() - p.stat().st_mtime > 86400:
                    p.unlink()
            except Exception:
                pass
    except Exception as e:
        report["cleanup"] = {"error": str(e)[:120]}
    summary = (
        f"Diagnóstico noturno {report['ts']}\n"
        f"pytest: {report['pytest']}\n"
        f"deps: {report['deps']}\n"
        f"cleanup: {report['cleanup']}"
    )
    send_telegram("*Engenheiro noturno*\n```\n" + summary[:3500] + "\n```", markdown=True)
    audit("night_engineer", tool="engenheiro_noturno", extra={"pytest_code": (report.get("pytest") or {}).get("code")})
    return report

def _loop():
    last = None
    while not _state["stop"].is_set():
        try:
            now = datetime.now()
            if now.hour == 2 and now.minute >= 30 and now.minute < 35 and last != now.date():
                run_diagnostic()
                last = now.date()
        except Exception as e:
            audit("night_loop_err", tool="engenheiro_noturno", extra={"error": str(e)[:120]})
        _state["stop"].wait(60)

def start_scheduler() -> bool:
    if _state["thread"] and _state["thread"].is_alive():
        return True
    _state["stop"] = threading.Event()
    t = threading.Thread(target=_loop, daemon=True, name="engenheiro-noturno")
    _state["thread"] = t
    t.start()
    return True

def run(parameters=None, player=None, **_ctx) -> str:
    action = str((parameters or {}).get("action") or "run_now").lower()
    if action == "start_scheduler":
        return done("engenheiro_noturno", scheduler=start_scheduler())
    if action == "stop_scheduler":
        _state["stop"].set()
        return done("engenheiro_noturno", scheduler=False)
    if action == "status":
        return done("engenheiro_noturno", scheduler=bool(_state["thread"] and _state["thread"].is_alive()))
    speak_short("Executando diagnóstico, Senhor.", player=player)
    report = run_diagnostic()
    return done("engenheiro_noturno", action="run_now", report=report)
