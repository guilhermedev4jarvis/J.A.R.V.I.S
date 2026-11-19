"""Windows power plans + brightness helpers; safe no-ops elsewhere."""
from __future__ import annotations

import platform
import re
import subprocess
from typing import Optional

from core.outcome import ask, done, failed, unverified

_OS = platform.system()


def _run(cmd: list[str], timeout: float = 12.0) -> tuple[int, str, str]:
    kw = {}
    if _OS == "Windows":
        kw["creationflags"] = 0x08000000
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:
        return 1, "", str(e)


def _list_plans() -> list[dict]:
    code, out, err = _run(["powercfg", "/list"])
    if code != 0:
        return []
    plans = []
    for line in out.splitlines():
        m = re.search(r"([0-9a-fA-F-]{36})\s+\(([^)]+)\)(\s+\*)?", line)
        if m:
            plans.append({"guid": m.group(1), "name": m.group(2), "active": bool(m.group(3))})
    return plans


def _set_plan(name_or_guid: str) -> tuple[bool, str]:
    plans = _list_plans()
    target = name_or_guid.lower().strip()
    match = None
    for p in plans:
        if target == p["guid"].lower() or target in p["name"].lower():
            match = p
            break
    if not match:
        return False, f"plan not found: {name_or_guid}"
    code, out, err = _run(["powercfg", "/setactive", match["guid"]])
    if code != 0:
        return False, err or out or "powercfg failed"
    return True, match["name"]


def _set_brightness(level: int) -> tuple[bool, str]:
    level = max(0, min(100, int(level)))
    # WMI via powershell
    ps = (
        f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
        f".WmiSetBrightness(1,{level})"
    )
    code, out, err = _run(["powershell", "-NoProfile", "-Command", ps], timeout=15)
    if code == 0:
        return True, f"brightness={level}"
    return False, err or out or "brightness unsupported on this device"


def run(parameters: Optional[dict] = None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or p.get("mode") or "list").strip().lower()

    if _OS != "Windows":
        return failed("power_profile_manager", "Windows-only action (powercfg)")

    if action in ("list", "show", "status"):
        plans = _list_plans()
        if not plans:
            return unverified("power_profile_manager", "could not list power plans")
        summary = ", ".join(f"{x['name']}{'*' if x['active'] else ''}" for x in plans)
        return done("power_profile_manager", op="list", plans=summary)

    if action in ("set", "activate", "profile"):
        name = str(p.get("profile") or p.get("name") or p.get("plan") or "").strip()
        if not name:
            return ask("power_profile_manager", "Qual plano? (ex: Balanced, High performance, Power saver)")
        ok, msg = _set_plan(name)
        return done("power_profile_manager", op="set", profile=msg) if ok else failed("power_profile_manager", msg)

    if action in ("brightness", "set_brightness"):
        if p.get("level") is None and p.get("value") is None and p.get("brightness") is None:
            return ask("power_profile_manager", "Qual brilho de 0 a 100?")
        level = p.get("level") if p.get("level") is not None else p.get("value", p.get("brightness"))
        ok, msg = _set_brightness(int(float(level)))
        return done("power_profile_manager", op="brightness", detail=msg) if ok else failed("power_profile_manager", msg)

    # presets
    if action in ("performance", "high"):
        ok, msg = _set_plan("high")
        return done("power_profile_manager", op="performance", profile=msg) if ok else failed("power_profile_manager", msg)
    if action in ("saver", "eco", "economy"):
        ok, msg = _set_plan("saver")
        if not ok:
            ok, msg = _set_plan("power saver")
        return done("power_profile_manager", op="saver", profile=msg) if ok else failed("power_profile_manager", msg)
    if action in ("balanced",):
        ok, msg = _set_plan("balanced")
        return done("power_profile_manager", op="balanced", profile=msg) if ok else failed("power_profile_manager", msg)

    return failed("power_profile_manager", f"unknown action {action}")
