"""
action_analytics — usage statistics for JARVIS actions.

Records (or reads) how often each action is called, success/failure counts,
and average duration. Helps decide what to optimise or what can be demoted
to a plugin.

Persistence: config/action_analytics.json
Other modules can call record_invocation() to feed data; this action only
exposes query / reset / summary.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from core.outcome import done, failed, ask

_BASE = Path(__file__).resolve().parents[2]
_STATE_PATH = _BASE / "config" / "action_analytics.json"
_lock = threading.RLock()  # re-entrant: handler may call record_invocation while holding lock


def _load() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "actions": {},
            "total_calls": 0,
        }


def _save(data: dict) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _record_into(data: dict, name: str, *, success: bool, duration_ms: float | None, error: str | None) -> None:
    """Mutate data dict in place (caller must hold the lock)."""
    acts = data.setdefault("actions", {})
    entry = acts.setdefault(name, {
        "calls": 0,
        "success": 0,
        "failed": 0,
        "total_ms": 0.0,
        "last_called": None,
        "last_error": None,
    })
    entry["calls"] += 1
    if success:
        entry["success"] += 1
    else:
        entry["failed"] += 1
        if error:
            entry["last_error"] = str(error)[:200]
    if duration_ms is not None:
        entry["total_ms"] = float(entry.get("total_ms") or 0) + float(duration_ms)
    entry["last_called"] = datetime.now().isoformat(timespec="seconds")
    data["total_calls"] = int(data.get("total_calls") or 0) + 1


def record_invocation(
    name: str,
    *,
    success: bool = True,
    duration_ms: float | None = None,
    error: str | None = None,
) -> None:
    """
    Public helper so action_loader or individual handlers can feed stats.
    Safe to call from any thread.
    """
    if not name:
        return
    with _lock:
        data = _load()
        _record_into(data, name, success=success, duration_ms=duration_ms, error=error)
        _save(data)


def _avg_ms(entry: dict) -> float | None:
    calls = entry.get("calls") or 0
    total = entry.get("total_ms") or 0
    if calls <= 0 or total <= 0:
        return None
    return round(total / calls, 1)


def action_analytics(parameters: dict | None = None, **_ctx) -> str:
    params = parameters or {}
    action = (params.get("action") or "summary").strip().lower()
    limit = int(params.get("limit") or 15)
    limit = max(3, min(limit, 50))

    with _lock:
        data = _load()

        # ── summary / top ─────────────────────────────────────────────────
        if action in ("summary", "top", "report", "status"):
            acts = data.get("actions") or {}
            if not acts:
                return done(
                    "action_analytics",
                    action="summary",
                    total_calls=0,
                    note="No usage data yet. Stats appear after actions are invoked.",
                )

            # Sort by call count descending
            ranked = sorted(
                acts.items(),
                key=lambda kv: (kv[1].get("calls") or 0, kv[1].get("total_ms") or 0),
                reverse=True,
            )[:limit]

            lines = []
            for name, e in ranked:
                avg = _avg_ms(e)
                avg_s = f"{avg}ms" if avg is not None else "n/a"
                fail = e.get("failed") or 0
                lines.append(
                    f"{name}: calls={e.get('calls', 0)} ok={e.get('success', 0)} "
                    f"fail={fail} avg={avg_s}"
                )

            # Also surface the slowest by average duration
            with_avg = [
                (n, e, _avg_ms(e))
                for n, e in acts.items()
                if _avg_ms(e) is not None
            ]
            slowest = sorted(with_avg, key=lambda t: t[2] or 0, reverse=True)[:5]
            slow_str = "; ".join(f"{n}={ms}ms" for n, _, ms in slowest) or "(n/a)"

            fail_heavy = [
                (n, e.get("failed", 0))
                for n, e in acts.items()
                if (e.get("failed") or 0) > 0
            ]
            fail_heavy.sort(key=lambda t: t[1], reverse=True)
            fail_str = "; ".join(f"{n}={c}" for n, c in fail_heavy[:5]) or "(none)"

            return done(
                "action_analytics",
                action="summary",
                total_calls=data.get("total_calls", 0),
                tracked_actions=len(acts),
                top= "; ".join(lines),
                slowest=slow_str,
                most_failures=fail_str,
                since=data.get("started_at"),
            )

        # ── detail for one action ─────────────────────────────────────────
        if action in ("detail", "info", "get"):
            name = (params.get("name") or params.get("action_name") or "").strip()
            if not name:
                return ask("action_analytics", "which action name?", hint="name=web_search")
            entry = (data.get("actions") or {}).get(name)
            if not entry:
                return done(
                    "action_analytics",
                    action="detail",
                    name=name,
                    note="no data recorded for this action yet",
                )
            return done(
                "action_analytics",
                action="detail",
                name=name,
                calls=entry.get("calls", 0),
                success=entry.get("success", 0),
                failed=entry.get("failed", 0),
                avg_ms=_avg_ms(entry),
                last_called=entry.get("last_called"),
                last_error=entry.get("last_error"),
            )

        # ── reset ─────────────────────────────────────────────────────────
        if action in ("reset", "clear"):
            confirm = str(params.get("confirm") or "").strip().lower() in ("1", "true", "yes", "y")
            if not confirm:
                return ask(
                    "action_analytics",
                    "This will erase all collected usage stats. Confirm?",
                    hint="Call again with confirm=true",
                )
            fresh = {
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "actions": {},
                "total_calls": 0,
            }
            _save(fresh)
            return done("action_analytics", action="reset", note="stats cleared")

        # ── record (manual / test) ────────────────────────────────────────
        if action in ("record", "log"):
            name = (params.get("name") or "").strip()
            if not name:
                return failed("action_analytics", "name is required for record")
            ok = str(params.get("success") or "true").lower() not in ("0", "false", "no")
            try:
                dur = float(params["duration_ms"]) if params.get("duration_ms") is not None else None
            except (TypeError, ValueError):
                dur = None
            _record_into(data, name, success=ok, duration_ms=dur, error=params.get("error"))
            _save(data)
            return done("action_analytics", action="record", name=name, success=ok)

    return ask(
        "action_analytics",
        "what should I do?",
        options="summary, detail (name=...), reset (confirm=true), record",
    )


TOOL = {
    "name": "action_analytics",
    "description": (
        "Shows usage analytics for JARVIS actions: most called, slowest, "
        "highest failure rate. Helps decide what to optimise or deprecate. "
        "Actions: summary (top list), detail (name=action_name), "
        "reset (confirm=true), record (manual entry). "
        "Other code can also call record_invocation() to feed live data."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "summary | detail | reset | record",
            },
            "name": {
                "type": "STRING",
                "description": "Action name for detail or record",
            },
            "limit": {
                "type": "NUMBER",
                "description": "How many top actions to show (default 15)",
            },
            "confirm": {
                "type": "STRING",
                "description": "true to confirm reset",
            },
            "success": {
                "type": "STRING",
                "description": "For record: true/false",
            },
            "duration_ms": {
                "type": "NUMBER",
                "description": "For record: execution time in ms",
            },
        },
        "required": [],
    },
    "handler": action_analytics,
    "tier": "core",
}
