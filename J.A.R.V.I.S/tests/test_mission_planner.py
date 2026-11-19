"""Unit tests for mission_planner — plan, chain, persist, resume, owner_gate."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import actions.ai_core._mission_planner_impl as impl
from actions.ai_core.mission_planner import TOOL, mission_planner


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(impl, "_MISSIONS", tmp_path / "desktop_missions")
    (tmp_path / "desktop_missions").mkdir(parents=True, exist_ok=True)
    # never speak in tests
    monkeypatch.setattr(impl, "_speak", lambda *a, **k: None)
    monkeypatch.setattr(impl, "_audit", lambda *a, **k: None)
    yield


def test_tool_contract():
    assert TOOL["name"] == "mission_planner"
    assert TOOL["parameters"]["type"] == "OBJECT"
    assert callable(TOOL["handler"])
    assert TOOL.get("risk") == "autonomous"


def test_handler_empty_asks_or_lists():
    r = mission_planner(parameters={"action": "list"})
    assert "status=done" in r
    r2 = mission_planner(parameters={"action": "plan_only"})
    assert "status=ask" in r2


def test_normalize_plan_valid_and_truncate():
    raw = {
        "steps": [
            {"step_id": f"s{i}", "tool_name": "web_search", "args": {"query": str(i)}, "description": f"d{i}"}
            for i in range(1, 12)
        ]
    }
    steps = impl._normalize_plan(raw, "goal")
    assert len(steps) == impl._MAX_STEPS
    assert steps[0]["status"] == "pending"


def test_normalize_plan_rejects_empty():
    with pytest.raises(ValueError):
        impl._normalize_plan({"steps": []}, "goal")
    with pytest.raises(ValueError):
        impl._normalize_plan({"steps": [{"no_tool": 1}]}, "goal")


def test_plan_only_persists(monkeypatch):
    monkeypatch.setattr(
        impl,
        "_llm_plan",
        lambda goal: impl._normalize_plan(
            {"steps": [
                {"tool_name": "web_search", "args": {"query": "rtx"}, "description": "search"},
                {"tool_name": "quick_note", "args": {"text": "{{previous_output}}"}, "description": "note"},
            ]},
            goal,
        ),
    )
    r = impl.create_plan("pesquisa rtx e salva", execute=False)
    assert "status=done" in r
    assert "mission_id=" in r
    items = impl._list_missions()
    assert len(items) == 1
    mid = items[0]["id"]
    m = impl._load(mid)
    assert m["goal"].startswith("pesquisa")
    assert len(m["steps"]) == 2
    assert m["status"] == "planned"


def test_chain_three_tools_context(monkeypatch):
    calls = []

    def fake_run(tool_name, params, player=None):
        calls.append((tool_name, dict(params)))
        return f"status=done action={tool_name} out={params.get('query') or params.get('text') or 'ok'}"

    monkeypatch.setattr(impl, "_run_tool", fake_run)
    monkeypatch.setattr(impl, "_owner_gate_ok", lambda *a, **k: (True, "ok"))

    steps = impl._normalize_plan(
        {"steps": [
            {"tool_name": "web_search", "args": {"query": "rtx 4070"}, "description": "s"},
            {"tool_name": "quick_note", "args": {"text": "{{previous_output}}"}, "description": "n"},
            {"tool_name": "clipboard_smart", "args": {"mode": "set", "text": "{{previous_output}}"}, "description": "c"},
        ]},
        "goal",
    )
    mission = {
        "id": "testchain1",
        "goal": "chain",
        "status": "planned",
        "created_ts": impl._ts(),
        "steps": steps,
        "last_output": None,
    }
    impl._save(mission)
    out = impl._execute_mission(mission, player=None, cancel=None)
    assert out["status"] == "completed"
    assert len(calls) == 3
    # second step received previous output injected into text
    assert "status=done action=web_search" in calls[1][1].get("text", "")
    assert calls[0][0] == "web_search"
    assert calls[2][0] == "clipboard_smart"


def test_resume_from_pending(monkeypatch):
    monkeypatch.setattr(impl, "_owner_gate_ok", lambda *a, **k: (True, "ok"))
    results = {"n": 0}

    def fake_run(tool_name, params, player=None):
        results["n"] += 1
        return f"status=done action={tool_name} n={results['n']}"

    monkeypatch.setattr(impl, "_run_tool", fake_run)

    steps = impl._normalize_plan(
        {"steps": [
            {"tool_name": "web_search", "args": {"query": "a"}, "description": "1"},
            {"tool_name": "quick_note", "args": {"text": "x"}, "description": "2"},
        ]},
        "g",
    )
    steps[0]["status"] = "completed"
    steps[0]["output"] = "status=done action=web_search prev"
    mission = {
        "id": "resume1",
        "goal": "g",
        "status": "failed",
        "created_ts": impl._ts(),
        "steps": steps,
        "last_output": steps[0]["output"],
    }
    impl._save(mission)

    # run resume synchronously by calling execute after reset like resume does
    for step in mission["steps"]:
        if step["status"] in ("failed", "blocked_by_security", "running"):
            step["status"] = "pending"
    out = impl._execute_mission(mission, player=None)
    assert out["status"] == "completed"
    # only second tool invoked (first already completed)
    assert results["n"] == 1


def test_owner_gate_blocks_sensitive(monkeypatch):
    monkeypatch.setattr(impl, "_owner_gate_ok", lambda *a, **k: (False, "denied"))

    def boom(*a, **k):
        raise AssertionError("tool must not run when blocked")

    monkeypatch.setattr(impl, "_run_tool", boom)
    steps = impl._normalize_plan(
        {"steps": [
            {"tool_name": "whatsapp_web", "args": {"mode": "open"}, "description": "wa", "requires_owner_gate": True},
        ]},
        "g",
    )
    mission = {
        "id": "sec1",
        "goal": "msg",
        "status": "planned",
        "created_ts": impl._ts(),
        "steps": steps,
        "last_output": None,
    }
    out = impl._execute_mission(mission)
    assert out["status"] == "blocked_by_security"
    assert out["steps"][0]["status"] == "blocked_by_security"


def test_heuristic_plan_max_steps():
    steps = impl._heuristic_plan("pesquisa preco rtx e salva arquivo e avisa no whatsapp")
    assert 1 <= len(steps) <= impl._MAX_STEPS
    tools = {s["tool_name"] for s in steps}
    assert "web_search" in tools or "quick_note" in tools
