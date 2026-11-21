"""Auditor estatistico de anomalias de CFTV."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from core.outcome import done

_BASE = Path(__file__).resolve().parents[2]
_AUDIT_DIR = _BASE / "memory" / "audit"
_RULES_PATH = _BASE / "config" / "event_rules.json"


def _collect_events() -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not _AUDIT_DIR.exists():
        return events
    for log_file in _AUDIT_DIR.glob("*.jsonl"):
        try:
            for line in log_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.strip():
                    events.append(json.loads(line))
        except Exception:
            continue
    return events


def _analyze_anomalies(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    hourly = Counter()
    night_events = []
    for ev in events:
        ts = ev.get("ts")
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts)
            hourly[dt.hour] += 1
            if 0 <= dt.hour <= 5:
                night_events.append({"hour": dt.hour, "event": ev.get("event", "unknown")})
    risk_level = "high" if len(night_events) >= 3 else ("medium" if night_events else "low")
    return {
        "total_events": len(events),
        "hourly_distribution": dict(sorted(hourly.items())),
        "night_anomalies_count": len(night_events),
        "night_anomalies": night_events[-10:],
        "risk_level": risk_level,
    }


def run(parameters=None, player=None, session_memory=None, **ctx):
    params = parameters or {}
    action = str(params.get("action") or "audit").lower()
    events = _collect_events()
    report = _analyze_anomalies(events)
    report["rules_loaded"] = _RULES_PATH.exists()

    if report["risk_level"] in ("medium", "high"):
        try:
            from core import event_bus
            if hasattr(event_bus, "publish"):
                event_bus.publish("security.cftv_anomaly", report)
        except Exception:
            pass

    msg = f"Auditoria CFTV ({action}): risco {report['risk_level']} com {report['night_anomalies_count']} evento(s) na madrugada."
    return done("auditor_cftv_anomalias", msg, report)