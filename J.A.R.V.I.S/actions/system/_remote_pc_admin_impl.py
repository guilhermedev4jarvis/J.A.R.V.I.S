
"""remote_pc_admin — screenshot, top processes, reboot, shell command."""
from __future__ import annotations
import os, platform, subprocess, time
from pathlib import Path
from core.outcome import done, failed, ask
from actions.security._security_vision import audit, capture_screen_png, env, send_telegram, speak_short
from core.owner_gate import password_ok, extract_password_from_text

def _shot():
    return capture_screen_png()

def _processes(n: int = 5) -> list:
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                info = p.info
                mem = (info.get("memory_info").rss / (1024 * 1024)) if info.get("memory_info") else 0
                procs.append({
                    "pid": info.get("pid"),
                    "name": info.get("name"),
                    "cpu": info.get("cpu_percent") or 0,
                    "mem_mb": round(mem, 1),
                })
            except Exception:
                continue
        # cpu_percent needs a prior call for accuracy; approximate by memory then cpu
        procs.sort(key=lambda x: (x["cpu"], x["mem_mb"]), reverse=True)
        return procs[:n]
    except Exception as e:
        audit("proc_fail", tool="remote_pc_admin", extra={"error": str(e)[:120]})
        return []

def _reboot() -> dict:
    if platform.system() != "Windows":
        return {"ok": False, "reason": "windows_only"}
    try:
        subprocess.Popen(["shutdown", "/r", "/t", "5"], creationflags=0x08000000 if os.name == "nt" else 0)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}

def _cmd(command: str) -> dict:
    command = (command or "").strip()
    if not command:
        return {"ok": False, "reason": "empty"}
    # basic blocklist
    blocked = ("format ", "del /f", "rm -rf /", "mkfs", "diskpart")
    low = command.lower()
    if any(b in low for b in blocked):
        return {"ok": False, "reason": "blocked_command"}
    try:
        kw = dict(capture_output=True, text=True, timeout=10, shell=True)
        if platform.system() == "Windows":
            kw["creationflags"] = 0x08000000
        r = subprocess.run(command, **kw)
        out = ((r.stdout or "") + (r.stderr or ""))[:3500]
        return {"ok": r.returncode == 0, "code": r.returncode, "output": out}
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout_10s"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}

def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "").lower()
    if action in ("screenshot", "tela"):
        cap = _shot()
        if cap.get("ok") and cap.get("path"):
            send_telegram("*Desktop* — captura atual", cap["path"], markdown=True)
            return done("remote_pc_admin", action="screenshot", file=cap.get("file"))
        return failed("remote_pc_admin", cap.get("reason", "capture_failed"))
    if action in ("processes", "processos"):
        top = _processes(5)
        return done("remote_pc_admin", action="processes", top=top)
    if action in ("reboot", "reiniciar"):
        pw = p.get("password") or extract_password_from_text(str(p.get("text") or ""))
        if not password_ok(pw):
            return failed("remote_pc_admin", "Reinício exige senha mestra, Senhor.")
        r = _reboot()
        if r.get("ok"):
            speak_short("Reiniciando o sistema em cinco segundos, Senhor.", player=player)
            return done("remote_pc_admin", action="reboot", **r)
        return failed("remote_pc_admin", r.get("reason", "reboot_failed"))
    if action == "cmd":
        cmd = str(p.get("command") or p.get("text") or "")
        pw = p.get("password") or extract_password_from_text(cmd) or extract_password_from_text(str(p.get("text") or ""))
        if not password_ok(pw):
            return failed("remote_pc_admin", "CMD exige senha mestra, Senhor.")
        # strip password tokens from command
        import re as _re
        cmd = _re.sub(r"(?:/senha|senha)\s+\S+", "", cmd, flags=_re.I).strip()
        r = _cmd(cmd)
        audit("remote_cmd", tool="remote_pc_admin", extra={"cmd": cmd[:80], "ok": r.get("ok")})
        if r.get("ok"):
            return done("remote_pc_admin", action="cmd", **r)
        return failed("remote_pc_admin", r.get("reason", "cmd_failed"), **{k: v for k, v in r.items() if k != "reason"})
    return ask("remote_pc_admin", "Screenshot, processos, reiniciar ou cmd, Senhor?")
