"""
core/network_fallback.py — detect cloud loss and prefer local engines.

Used by the main loop / provider registry to switch from Gemini Live (or
OpenAI Realtime) to the offline pipeline without a manual settings trip.
"""
from __future__ import annotations

import os
import socket
import threading
import time
from typing import Optional

_LOCK = threading.Lock()
_last_ok: Optional[float] = None
_last_check: float = 0.0
_CACHE_SECONDS = 5.0
_PROBE_HOSTS = (
    ("8.8.8.8", 53),
    ("1.1.1.1", 53),
)


def internet_reachable(timeout: float = 1.2) -> bool:
    """Cheap UDP/TCP probe; cached briefly to avoid hammering on every tool call."""
    global _last_ok, _last_check
    now = time.monotonic()
    with _LOCK:
        if now - _last_check < _CACHE_SECONDS and _last_ok is not None:
            return _last_ok
    ok = False
    for host, port in _PROBE_HOSTS:
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            ok = True
            break
        except OSError:
            continue
    with _LOCK:
        _last_ok = ok
        _last_check = now
    return ok


def should_use_local(*, air_gapped: bool = False, force_local: bool = False) -> tuple[bool, str]:
    """Return (use_local, reason)."""
    if force_local:
        return True, "force_local"
    if air_gapped:
        return True, "air_gapped"
    if not internet_reachable():
        return True, "network_unreachable"
    return False, "cloud_ok"


def reset_cache() -> None:
    global _last_ok, _last_check
    with _LOCK:
        _last_ok = None
        _last_check = 0.0


_force_local = False
_force_lock = threading.Lock()


def set_force_local(value: bool) -> None:
    global _force_local
    with _force_lock:
        _force_local = bool(value)
    reset_cache()


def is_force_local() -> bool:
    with _force_lock:
        if _force_local:
            return True
    return (os.getenv("JARVIS_FORCE_LOCAL") or "").strip() in ("1", "true", "yes")


# patch should_use_local via wrapper
_orig_should = should_use_local


def should_use_local(*, air_gapped: bool = False, force_local: bool = False) -> tuple[bool, str]:
    if is_force_local() or force_local:
        return True, "offline_mode"
    # also honor memory/offline_state.json
    try:
        from actions.ai_core._offline_impl import is_offline
        if is_offline():
            return True, "offline_mode"
    except Exception:
        pass
    return _orig_should(air_gapped=air_gapped, force_local=force_local)
