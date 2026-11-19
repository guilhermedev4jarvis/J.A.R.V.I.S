
"""offline action + MCP config + force local."""
from __future__ import annotations
from pathlib import Path
import json

import actions.ai_core.offline as offline
import actions.ai_core.mcp_manager as mcp_manager
from core.network_fallback import should_use_local, set_force_local
from core import mcp_client


def test_offline_toggle(tmp_path, monkeypatch):
    # isolate state file
    import actions.ai_core._offline_impl as impl
    monkeypatch.setattr(impl, "_STATE", tmp_path / "offline_state.json")
    r = offline.offline({"action": "enable"})
    assert "offline" in r and "status=done" in r
    assert impl.is_offline() is True
    use, reason = should_use_local()
    assert use is True
    r2 = offline.offline({"action": "disable"})
    assert impl.is_offline() is False


def test_mcp_servers_config_present():
    root = Path(__file__).resolve().parents[1]
    cfg = root / "config" / "mcp_servers.json"
    assert cfg.is_file()
    data = json.loads(cfg.read_text(encoding="utf-8"))
    servers = data["servers"]
    if isinstance(servers, dict):
        names = set(servers.keys())
        local = [s for s in servers.values() if not s.get("requires_internet")]
    else:
        names = {s["name"] for s in servers}
        local = [s for s in servers if not s.get("requires_internet")]
    assert {"filesystem", "memory", "fetch"} <= names
    # local servers that are enabled should stay enabled
    assert any(s.get("enabled", True) for s in local)


def test_mcp_manager_list():
    r = mcp_manager.mcp_manager({"action": "list"})
    assert "status=done" in r


def test_mcp_apply_offline_policy():
    assert hasattr(mcp_client, "apply_offline_policy")
    out = mcp_client.apply_offline_policy(True)
    assert "paused" in out
    mcp_client.apply_offline_policy(False)


def test_no_mainlocal():
    root = Path(__file__).resolve().parents[1]
    assert not (root / "mainlocal.py").exists()
    assert not (root / "core" / "offline_assistant.py").exists()
