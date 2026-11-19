"""
core/audit.py — append-only audit log for irreversible / high-stakes actions.

Each line is a JSON object. Files rotate by day under memory/audit/.
Secrets are redacted before write.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.redaction import redact_mapping, redact_text

_BASE = Path(__file__).resolve().parents[1]
_AUDIT_DIR = _BASE / "memory" / "audit"
_LOCK = threading.Lock()
_MAX_LINE = 4000


def _day_path(when: Optional[datetime] = None) -> Path:
    when = when or datetime.now(timezone.utc)
    return _AUDIT_DIR / f"audit_{when.strftime('%Y-%m-%d')}.jsonl"


def log_event(
    kind: str,
    *,
    tool: str = "",
    args: Optional[dict] = None,
    result: str = "",
    user: str = "",
    extra: Optional[dict] = None,
) -> None:
    """Append one audit event. Never raises to callers."""
    try:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": str(kind)[:80],
            "tool": str(tool)[:120],
            "user": str(user)[:80],
        }
        if args:
            payload["args"] = redact_mapping(args)
        if result:
            payload["result"] = redact_text(result)[:1500]
        if extra:
            payload["extra"] = redact_mapping(extra)

        line = json.dumps(payload, ensure_ascii=False, default=str)
        if len(line) > _MAX_LINE:
            line = line[:_MAX_LINE] + "…"

        path = _day_path()
        with _LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception as e:
        # Last-resort stderr; never break the tool path for logging.
        print(f"[audit] write failed: {e}")


def log_tool(
    tool: str,
    args: Optional[dict],
    result: str,
    *,
    risk: str = "review",
    confirmed: bool = False,
) -> None:
    log_event(
        "tool",
        tool=tool,
        args=args,
        result=result,
        extra={"risk": risk, "confirmed": confirmed},
    )


def log_confirm(tool: str, accepted: bool, args: Optional[dict] = None) -> None:
    log_event(
        "confirm",
        tool=tool,
        args=args,
        extra={"accepted": accepted},
    )


def recent(limit: int = 30) -> list[dict]:
    """Return the last *limit* events from today's log (best-effort)."""
    path = _day_path()
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines[-max(1, limit):]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []
