"""Presença prolongada / modo viagem — ausência coletiva >6h dos residentes."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Optional

_BASE = Path(__file__).resolve().parents[2]
_STATE = _BASE / "memory" / "presence_travel_state.json"
_lock = threading.Lock()
_RESIDENT_TAGS = ("owner", "dono", "mae", "mãe", "familia", "pai", "esposa")

try:
    from core.event_bus import publish as _eb_pub
except Exception:
    def _eb_pub(*_a, **_k):
        pass


def _load() -> dict:
    if not _STATE.is_file():
        return {"away_since": None, "extended_away": False, "last_resident_seen": None}
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"away_since": None, "extended_away": False, "last_resident_seen": None}


def _save(data: dict) -> None:
    with _lock:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_resident_tag(tag: str) -> bool:
    t = (tag or "").lower().strip()
    return any(r in t for r in _RESIDENT_TAGS) or t in _RESIDENT_TAGS


def residents_present(devices: list[dict], known: dict) -> list[str]:
    """Return resident tags currently on Wi-Fi."""
    present = []
    for d in devices or []:
        mac = (d.get("mac") or "").lower()
        tag = str(known.get(mac) or d.get("owner_tag") or d.get("name") or "").lower()
        if is_resident_tag(tag):
            present.append(tag)
    return present


def update_presence(devices: list[dict], known: dict, away_hours: float = 6.0) -> dict:
    """Track collective absence; emit extended_away events when thresholds cross."""
    present = residents_present(devices, known)
    now = time.time()
    data = _load()
    was = bool(data.get("extended_away"))

    if present:
        data["last_resident_seen"] = now
        data["away_since"] = None
        if was:
            data["extended_away"] = False
            _save(data)
            _eb_pub("presence.extended_away_deactivated", residents=present)
            return {"extended_away": False, "residents": present, "deactivated": True}
        _save(data)
        return {"extended_away": False, "residents": present}

    # no residents
    if data.get("away_since") is None:
        data["away_since"] = now
    elapsed_h = (now - float(data["away_since"])) / 3600.0
    if elapsed_h >= away_hours and not was:
        data["extended_away"] = True
        _save(data)
        _eb_pub("presence.extended_away_activated", away_hours=round(elapsed_h, 2))
        return {"extended_away": True, "activated": True, "away_hours": elapsed_h}
    _save(data)
    return {"extended_away": was, "away_hours": elapsed_h, "residents": []}


def is_extended_away() -> bool:
    return bool(_load().get("extended_away"))


def require_double_confirm_for_gate() -> bool:
    """When traveling, gate open requires owner_gate / confirm."""
    return is_extended_away()
