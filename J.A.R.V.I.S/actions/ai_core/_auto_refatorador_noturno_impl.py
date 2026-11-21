"""Analisador noturno de gargalos e saude das actions."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from core.outcome import done

_BASE = Path(__file__).resolve().parents[2]
_ANALYTICS_PATH = _BASE / "config" / "action_analytics.json"
_REPORT_PATH = _BASE / "memory" / "nightly_refactor_report.json"


def _analyze_analytics(threshold_ms: float) -> Dict[str, Any]:
    if not _ANALYTICS_PATH.exists():
        return {"tracked_actions": 0, "slow_actions": [], "failing_actions": []}
    try:
        raw = json.loads(_ANALYTICS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"tracked_actions": 0, "slow_actions": [], "failing_actions": []}

    slow = []
    failing = []
    items = raw.items() if isinstance(raw, dict) else []
    for name, stats in items:
        if not isinstance(stats, dict):
            continue
        avg_ms = float(stats.get("avg_ms") or stats.get("latency_ms") or 0)
        errors = int(stats.get("errors") or stats.get("failures") or 0)
        if avg_ms >= threshold_ms:
            slow.append({"action": name, "avg_ms": avg_ms})
        if errors > 0:
            failing.append({"action": name, "errors": errors})

    return {"tracked_actions": len(list(items)), "slow_actions": slow, "failing_actions": failing}


def run(parameters=None, player=None, session_memory=None, **ctx):
    params = parameters or {}
    action = str(params.get("action") or "analyze").lower()
    threshold = float(params.get("slow_threshold_ms") or 1500)

    if action == "last_report" and _REPORT_PATH.exists():
        data = json.loads(_REPORT_PATH.read_text(encoding="utf-8"))
        return done("auto_refatorador_noturno", "Ultimo relatorio noturno carregado.", data)

    test_summary = "skipped"
    if action == "run_tests":
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_action_contracts.py", "-q"],
            cwd=str(_BASE),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        test_summary = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else f"exit={proc.returncode}"

    perf = _analyze_analytics(threshold)
    report = {
        "generated_at": datetime.now().isoformat(),
        "test_summary": test_summary,
        "threshold_ms": threshold,
        **perf,
    }
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return done(
        "auto_refatorador_noturno",
        f"Auditoria concluida: {len(perf['slow_actions'])} action(s) lenta(s) e {len(perf['failing_actions'])} com falha.",
        report,
    )