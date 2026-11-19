"""
Action: battery — battery charge level, charging state, time remaining.
"""
from __future__ import annotations

import platform
from typing import Optional

try:
    import psutil
    _HAS = True
except ImportError:
    _HAS = False


def _log(msg: str, player=None) -> None:
    print(f"[Battery] {msg}")
    if player:
        try:
            player.write_log(f"JARVIS: {msg}")
        except Exception:
            pass


def _secs_human(secs: Optional[int]) -> str:
    if secs is None or secs < 0:
        return ""
    h, rem = divmod(int(secs), 3600)
    m = rem // 60
    if h and m:
        return f"{h}h {m}min"
    if h:
        return f"{h}h"
    return f"{m} minutes"


def battery_action(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    if not _HAS:
        return "Sir, battery status needs the psutil package."

    try:
        bat = psutil.sensors_battery()
    except Exception as e:
        return f"Sir, could not read battery sensors: {e}"

    if bat is None:
        # Desktop without battery
        msg = (
            "This machine has no battery sensor — it looks like a desktop "
            "or the OS is not exposing battery data."
        )
        _log(msg, player)
        return msg

    pct = bat.percent
    plugged = bat.power_plugged
    secs = bat.secsleft

    # psutil uses -1 for unknown, -2 for unlimited (charging)
    time_bit = ""
    if not plugged and secs is not None and secs > 0:
        time_bit = f" About {_secs_human(secs)} remaining."
    elif plugged and secs is not None and secs > 0:
        time_bit = f" About {_secs_human(secs)} to full charge."

    if plugged:
        state = "charging" if pct < 99.5 else "fully charged and plugged in"
    else:
        state = "on battery"

    # Gentle advice thresholds
    advice = ""
    if not plugged and pct <= 15:
        advice = " You may want to plug in soon."
    elif not plugged and pct <= 5:
        advice = " Battery is critically low."

    msg = f"Battery at {pct:.0f}%, {state}.{time_bit}{advice}"
    _log(msg, player)
    return msg


TOOL = {
    "name": "battery",
    "description": (
        "Reports battery charge percentage, whether the laptop is plugged in, "
        "and estimated time remaining or time to full charge. "
        "Use when the user asks about battery, power, charge level, or "
        "how long until the battery runs out."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
    "handler": battery_action,
}
