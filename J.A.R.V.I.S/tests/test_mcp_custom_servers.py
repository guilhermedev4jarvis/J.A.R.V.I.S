"""MCP custom servers: config schema + local JSON-RPC tools/list and tools/call."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_mcp_servers_json_schema_loads():
    from core import mcp_client

    servers = mcp_client._load_server_list()
    names = {s.get("name") for s in servers}
    # enabled servers should include local ones
    assert "obs_studio" in names
    assert "ai_training" in names
    assert "icsee_cameras" in names
    assert "github" in names
    assert "youtube" in names
    # playwright is disabled
    assert "playwright" not in names


def test_mcp_manager_list_done():
    import actions.ai_core.mcp_manager as mcp_manager

    r = mcp_manager.mcp_manager({"action": "list"})
    assert "status=done" in r


def _rpc_call(script: Path, messages: list[dict]) -> list[dict]:
    proc = subprocess.Popen(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload = "\n".join(json.dumps(m) for m in messages) + "\n"
    out, err = proc.communicate(payload, timeout=15)
    lines = [ln for ln in (out or "").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def test_obs_mcp_tools_list_and_status():
    script = ROOT / "mcp_servers" / "obs_mcp_server.py"
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "obs_get_status", "arguments": {}},
        },
    ]
    res = _rpc_call(script, msgs)
    assert any(r.get("id") == 2 and "tools" in (r.get("result") or {}) for r in res)
    tools = next(r["result"]["tools"] for r in res if r.get("id") == 2)
    names = {t["name"] for t in tools}
    assert "obs_switch_scene" in names
    assert "obs_start_recording" in names
    status = next(r for r in res if r.get("id") == 3)
    assert "result" in status or "error" in status


def test_ai_training_mcp_list_models_and_jobs():
    script = ROOT / "mcp_servers" / "ai_training_mcp_server.py"
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "train_start_job", "arguments": {"name": "dry1"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "train_list_jobs", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "train_list_local_models", "arguments": {}},
        },
    ]
    res = _rpc_call(script, msgs)
    tools = next(r["result"]["tools"] for r in res if r.get("id") == 1)
    assert {t["name"] for t in tools} >= {
        "train_list_jobs",
        "train_start_job",
        "train_gpu_metrics",
        "train_list_local_models",
    }
    start = next(r for r in res if r.get("id") == 2)
    assert "result" in start


def test_icsee_mcp_list_and_rois():
    script = ROOT / "mcp_servers" / "icsee_mcp_server.py"
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "icsee_list_cameras", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "icsee_get_rois_and_tripwires", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "icsee_check_stream_health", "arguments": {}},
        },
    ]
    res = _rpc_call(script, msgs)
    tools = next(r["result"]["tools"] for r in res if r.get("id") == 1)
    names = {t["name"] for t in tools}
    assert "icsee_capture_snapshot" in names
    cams = next(r for r in res if r.get("id") == 2)
    text = cams["result"]["content"][0]["text"]
    data = json.loads(text)
    assert data.get("ok") is True
    assert isinstance(data.get("cameras"), list)


def test_env_expand_defaults(monkeypatch):
    from core.mcp_client import _expand_env

    monkeypatch.delenv("OBS_WS_PORT", raising=False)
    assert _expand_env("${OBS_WS_PORT:-4455}") == "4455"
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    assert _expand_env("${GITHUB_TOKEN}") == "ghp_test"
