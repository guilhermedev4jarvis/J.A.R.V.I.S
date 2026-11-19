"""
system_health — CPU, RAM, disk, top processes, and a short actionable summary.

Builds on psutil (already a hard dependency). Never claims a remediation
happened unless it actually did.
"""
from __future__ import annotations

import platform
from pathlib import Path

from core.outcome import done, failed

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

_OS = platform.system()


def _top_processes(n: int = 8) -> list[dict]:
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            info = p.info
            mem = info.get("memory_info")
            rss = getattr(mem, "rss", 0) if mem else 0
            procs.append({
                "pid": info.get("pid"),
                "name": info.get("name") or "?",
                "cpu": float(info.get("cpu_percent") or 0.0),
                "rss_mb": round(rss / (1024 * 1024), 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    # cpu_percent needs a previous sample; call once more after a tiny sleep
    import time
    time.sleep(0.15)
    for p in psutil.process_iter(["pid", "cpu_percent"]):
        try:
            pid = p.info["pid"]
            cpu = float(p.info.get("cpu_percent") or 0.0)
            for row in procs:
                if row["pid"] == pid:
                    row["cpu"] = cpu
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda r: (r["cpu"], r["rss_mb"]), reverse=True)
    return procs[:n]


def _disk_summary() -> list[dict]:
    rows = []
    for part in psutil.disk_partitions(all=False):
        try:
            if _OS == "Windows" and ("cdrom" in part.opts or part.fstype == ""):
                continue
            usage = psutil.disk_usage(part.mountpoint)
            rows.append({
                "mount": part.mountpoint,
                "total_gb": round(usage.total / (1024 ** 3), 1),
                "used_pct": usage.percent,
                "free_gb": round(usage.free / (1024 ** 3), 1),
            })
        except (PermissionError, FileNotFoundError, OSError):
            continue
    return rows


def _suggestions(cpu: float, mem_pct: float, disks: list[dict], top: list[dict]) -> list[str]:
    tips = []
    if cpu >= 85:
        heavy = ", ".join(f"{p['name']}({p['cpu']:.0f}%)" for p in top[:3] if p["cpu"] >= 10)
        tips.append(f"CPU is high ({cpu:.0f}%). Heaviest: {heavy or 'unknown'}.")
    if mem_pct >= 85:
        tips.append(f"Memory is high ({mem_pct:.0f}%). Consider closing unused apps.")
    for d in disks:
        if d["used_pct"] >= 90:
            tips.append(
                f"Disk {d['mount']} is {d['used_pct']:.0f}% full "
                f"({d['free_gb']} GB free)."
            )
    if not tips:
        tips.append("System resources look normal.")
    return tips


def system_health(parameters=None, **_ctx) -> str:
    if not _HAS_PSUTIL:
        return failed("system_health", "psutil is not installed")

    params = parameters or {}
    detail = (params.get("detail") or "summary").strip().lower()

    try:
        cpu = float(psutil.cpu_percent(interval=0.25))
        mem = psutil.virtual_memory()
        disks = _disk_summary()
        top = _top_processes(8) if detail in ("full", "processes", "summary") else []
    except Exception as e:
        return failed("system_health", f"could not sample system: {e}")

    tips = _suggestions(cpu, mem.percent, disks, top)

    top_str = "; ".join(
        f"{p['name']} cpu={p['cpu']:.0f}% ram={p['rss_mb']}MB"
        for p in top[:6]
    ) or "(n/a)"

    disk_str = "; ".join(
        f"{d['mount']} {d['used_pct']:.0f}% used ({d['free_gb']}G free)"
        for d in disks[:4]
    ) or "(n/a)"

    return done(
        "system_health",
        cpu_percent=round(cpu, 1),
        memory_percent=round(mem.percent, 1),
        memory_used_gb=round(mem.used / (1024 ** 3), 2),
        memory_total_gb=round(mem.total / (1024 ** 3), 2),
        disks=disk_str,
        top_processes=top_str,
        advice=" | ".join(tips),
    )


_LEGACY_TOOL = {
    "name": "system_health",
    "description": (
        "Reports CPU, memory, disk usage, top processes and short advice. "
        "Use when the user asks if the computer is slow, how much RAM is free, "
        "what is using the CPU, or for a general system health check. "
        "This tool only observes — it does not kill processes or free disk "
        "space by itself."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "detail": {
                "type": "STRING",
                "description": "summary (default) or full",
            },
        },
        "required": [],
    },
    "handler": system_health,
    "tier": "core",
}
