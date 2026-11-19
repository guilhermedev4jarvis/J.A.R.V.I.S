"""
Tests for quality layers: contracts, retry, sandbox, redaction, agent_mode, memory hygiene.

Run:  python -m pytest tests/test_quality_layers.py -q
or:   python tests/test_quality_layers.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_contracts_parse_and_risk():
    from core.contracts import parse_tool_dict, assert_outcome, validate_outcome_string

    good = parse_tool_dict({
        "name": "demo_tool",
        "description": "A demo",
        "parameters": {"type": "OBJECT", "properties": {}},
        "risk": "safe",
    })
    assert good.valid
    assert good.risk == "safe"

    bad = parse_tool_dict({"name": "!!!", "description": ""})
    assert not bad.valid

    assert assert_outcome("status=done action=x") == "done"
    assert validate_outcome_string("hello")  # missing status


def test_retry_and_circuit():
    from core.retry import retry_call, circuit_breaker, reset_circuit

    n = {"c": 0}

    def flaky():
        n["c"] += 1
        if n["c"] < 3:
            raise RuntimeError("temp")
        return "ok"

    assert retry_call(flaky, attempts=4, base_delay=0.01) == "ok"

    reset_circuit("t1")
    with circuit_breaker("t1", failure_threshold=2, reset_seconds=30) as gate:
        assert gate.allow()
        gate.record(False)
        gate.record(False)
        assert not gate.allow()
    reset_circuit("t1")


def test_redaction_masks_keys():
    from core.redaction import redact_text, redact_mapping

    s = redact_text("Authorization: Bearer sk-abc1234567890123456789 and password=secret123")
    assert "sk-abc" not in s
    assert "secret123" not in s
    assert "***" in s

    m = redact_mapping({"api_key": "AIzaSyDummyKeyValue123456", "note": "ok"})
    assert m["api_key"] == "***"
    assert m["note"] == "ok"


def test_sandbox_path_policy():
    from core.sandbox import path_is_allowed, dry_run_mode, is_dry_run, precheck

    ok, _ = path_is_allowed(str(Path.home() / "Documents" / "x.txt"))
    # Documents may or may not exist; alias always ok
    ok2, reason = path_is_allowed("desktop")
    assert ok2

    with dry_run_mode(True):
        assert is_dry_run()
        msg = precheck("file_controller", {"action": "delete", "path": "/tmp/x"}, risk="destructive")
        assert msg and msg.startswith("dry_run:")
    assert not is_dry_run()


def test_agent_mode_listen_blocks_actuation():
    from core import agent_mode

    prev = agent_mode.get_mode()
    try:
        agent_mode.set_mode("listen")
        allowed, why = agent_mode.tool_allowed("file_controller", risk="review")
        assert not allowed
        allowed2, _ = agent_mode.tool_allowed("recall_memory", risk="safe")
        assert allowed2
        agent_mode.set_mode("assist")
        allowed3, _ = agent_mode.tool_allowed("file_controller", risk="review")
        assert allowed3
    finally:
        agent_mode.set_mode(prev)


def test_memory_hygiene_apis():
    from memory.memory_manager import (
        memory_hygiene_report,
        detect_contradictions,
        episode_stats,
        consolidate_episodes,
    )
    report = memory_hygiene_report()
    assert isinstance(report, str) and "Episodes" in report
    assert isinstance(detect_contradictions(), list)
    stats = episode_stats()
    assert "episodes" in stats
    # consolidate should not raise
    consolidate_episodes()


def test_outcome_helpers():
    from core.outcome import done, failed, is_problem
    assert "status=done" in done("x", note="y")
    assert is_problem(failed("x", "nope"))


if __name__ == "__main__":
    test_contracts_parse_and_risk()
    test_retry_and_circuit()
    test_redaction_masks_keys()
    test_sandbox_path_policy()
    test_agent_mode_listen_blocks_actuation()
    test_memory_hygiene_apis()
    test_outcome_helpers()
    print("OK — quality layers passed")
