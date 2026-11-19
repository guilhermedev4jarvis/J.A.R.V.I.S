"""
Action: process_manager — list heavy processes or terminate by name.
"""
from __future__ import annotations

import platform
from typing import Optional

try:
    import psutil
    _HAS = True
except ImportError:
    _HAS = False

# Names we refuse to kill (safety)
_PROTECTED = {
    "system", "system idle process", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "svchost.exe", "winlogon.exe",
    "explorer.exe", "dwm.exe", "fontdrvhost.exe",
    "systemd", "init", "kernel", "launchd",
    "python", "python.exe", "pythonw.exe",  # avoid killing the assistant itself carelessly
}


def _log(msg: str, player=None) -> None:
    print(f"[Process] {msg}")
    if player:
        try:
            player.write_log(f"JARVIS: {msg}")
        except Exception:
            pass


def _list_top(by: str = "cpu", limit: int = 8) -> str:
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            info = p.info
            name = info.get("name") or "?"
            cpu = info.get("cpu_percent") or 0.0
            mem = 0.0
            mi = info.get("memory_info")
            if mi is not None:
                mem = getattr(mi, "rss", 0) / (1024 * 1024)
            procs.append((name, info.get("pid"), cpu, mem))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # cpu_percent is 0 on first call unless we interval — do a short sample
    if by == "cpu":
        # refresh with a tiny interval for more meaningful numbers
        try:
            for p in psutil.process_iter():
                try:
                    p.cpu_percent(interval=None)
                except Exception:
                    pass
            import time
            time.sleep(0.35)
            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
                try:
                    info = p.info
                    name = info.get("name") or "?"
                    cpu = info.get("cpu_percent") or 0.0
                    mem = 0.0
                    mi = info.get("memory_info")
                    if mi is not None:
                        mem = getattr(mi, "rss", 0) / (1024 * 1024)
                    procs.append((name, info.get("pid"), cpu, mem))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass

    key = (lambda x: x[2]) if by == "cpu" else (lambda x: x[3])
    procs.sort(key=key, reverse=True)
    top = procs[: max(1, min(limit, 15))]

    if not top:
        return "Could not list processes, sir."

    lines = []
    for name, pid, cpu, mem in top:
        lines.append(f"{name} (pid {pid}): CPU {cpu:.0f}%, RAM {mem:.0f} MB")
    header = "Top processes by CPU:" if by == "cpu" else "Top processes by memory:"
    return header + "\n" + "\n".join(lines)


def _kill_by_name(name: str) -> str:
    if is_protected_process(name):
        return f"Sir, I refuse to terminate protected process '{name}'."
    target = name.strip().lower()
    if not target:
        return "Sir, provide the process name to terminate."

    # strip .exe for comparison convenience
    target_base = target[:-4] if target.endswith(".exe") else target
    if target in _PROTECTED or target_base in _PROTECTED:
        return f"Sir, I refuse to terminate protected process '{name}'."

    killed = []
    denied = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            pname = (p.info.get("name") or "").lower()
            pbase = pname[:-4] if pname.endswith(".exe") else pname
            if pname == target or pbase == target_base or target_base in pbase:
                # extra guard: never kill our own pid
                if p.pid == psutil.Process().pid:
                    continue
                try:
                    p.terminate()
                    killed.append(f"{p.info.get('name')} ({p.pid})")
                except psutil.AccessDenied:
                    denied.append(pname)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if killed:
        # give them a moment, then kill -9 leftovers
        import time
        time.sleep(0.6)
        for p in psutil.process_iter(["pid", "name"]):
            try:
                pname = (p.info.get("name") or "").lower()
                pbase = pname[:-4] if pname.endswith(".exe") else pname
                if (pname == target or pbase == target_base) and p.pid != psutil.Process().pid:
                    try:
                        p.kill()
                    except Exception:
                        pass
            except Exception:
                pass
        return f"Terminated: {', '.join(killed)}."
    if denied:
        return f"Permission denied for: {', '.join(denied)}. Try running as admin."
    return f"No running process matched '{name}'."


def process_manager_action(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    if not _HAS:
        return "Sir, process_manager needs the psutil package."

    action = (parameters.get("action") or "list").strip().lower()
    by = (parameters.get("sort_by") or "cpu").strip().lower()
    if by not in ("cpu", "memory", "ram"):
        by = "cpu"
    if by == "ram":
        by = "memory"

    try:
        if action in ("list", "top", "status"):
            limit = 8
            try:
                if parameters.get("limit") is not None:
                    limit = int(parameters["limit"])
            except (TypeError, ValueError):
                pass
            msg = _list_top(by=by, limit=limit)
            _log(msg.split("\n")[0], player)
            return msg

        if action in ("kill", "terminate", "end", "close"):
            name = parameters.get("name") or parameters.get("process") or ""
            msg = _kill_by_name(str(name))
            _log(msg, player)
            return msg

        return "Sir, use action list or kill. For kill, provide the process name."
    except Exception as e:
        return f"Sir, process_manager failed: {e}"


TOOL = {
    "name": "process_manager",
    "description": (
        "Lists the processes using the most CPU or memory, or terminates a "
        "process by name. Use for 'what is eating my CPU', 'kill chrome', "
        "'close discord'. Refuses to kill critical system processes. "
        "Actions: list (default), kill."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "list | kill",
            },
            "name": {
                "type": "STRING",
                "description": "Process name to terminate (for action=kill), e.g. 'chrome' or 'notepad.exe'",
            },
            "sort_by": {
                "type": "STRING",
                "description": "cpu (default) | memory — for list",
            },
            "limit": {
                "type": "NUMBER",
                "description": "How many processes to show (default 8, max 15)",
            },
        },
        "required": [],
    },
    "handler": process_manager_action,
}
