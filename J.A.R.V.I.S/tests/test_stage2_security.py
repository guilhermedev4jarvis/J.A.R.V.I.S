"""Stage 2 security: liveness API shape, session lock, secrets vault."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_face_liveness_result_dataclass():
    from core.face_auth import LivenessResult
    r = LivenessResult(False, "static_or_photo_suspected", motion_score=0.1)
    assert r.ok is False


def test_session_lock_timeout(monkeypatch):
    from core import owner_gate as og
    og.configure_idle_timeout(60)
    og.touch_activity()
    assert og.is_session_locked() is False
    # force past idle
    with og._lock_mu:
        og._lock_state["last_activity"] = time.time() - 120
        og._lock_state["idle_sec"] = 60
        og._lock_state["locked"] = False
    assert og.is_session_locked() is True
    og.touch_activity()
    assert og.is_session_locked() is False


def test_critical_names():
    from core.owner_gate import is_critical
    assert is_critical("powershell_cmd", "run")
    assert is_critical("whatsapp_web", "")
    assert is_critical("", "shutdown")
    assert not is_critical("web_search", "search")


def test_secrets_vault_roundtrip(tmp_path, monkeypatch):
    from core import secrets as sec
    monkeypatch.setattr(sec, "VAULT_FILE", tmp_path / "secrets.vault")
    monkeypatch.setattr(sec, "CONFIG_FILE", tmp_path / "api_keys.json")
    monkeypatch.setattr(sec, "_migrated", False)
    monkeypatch.setattr(sec, "_env_get", lambda *a, **k: "")
    monkeypatch.setattr(sec, "load_dotenv_once", lambda: None)
    # Isolate from host env secrets (GEMINI_API_KEY etc.)
    for k in list(__import__("os").environ):
        if "KEY" in k.upper() or "SECRET" in k.upper() or "TOKEN" in k.upper() or "GEMINI" in k.upper():
            monkeypatch.delenv(k, raising=False)
    # plain config with key
    sec.CONFIG_FILE.write_text(
        json.dumps({"gemini_api_key": "test-secret-key-123", "theme": "dark"}),
        encoding="utf-8",
    )
    report = sec.migrate_plain_secrets()
    assert report.get("migrated")
    assert "gemini_api_key" in report.get("moved", [])
    cfg = json.loads(sec.CONFIG_FILE.read_text(encoding="utf-8"))
    assert cfg.get("gemini_api_key") == ""
    assert sec.get_secret("gemini_api_key") == "test-secret-key-123"


def test_verify_from_camera_liveness_fail(monkeypatch):
    from core import face_auth as fa
    monkeypatch.setattr(
        fa,
        "check_liveness",
        lambda *a, **k: (fa.LivenessResult(False, "static_or_photo_suspected", 0.0), None),
    )
    score = fa.verify_from_camera(require_liveness=True)
    assert score.accepted is False
    assert "liveness_failed" in score.detail


def test_critical_consolidated_names():
    from core.owner_gate import is_critical
    assert is_critical("powershell_tool", "execute")
    assert is_critical("file_manager", "delete")
    assert is_critical("code_studio", "self")
    assert is_critical("whatsapp_web", "")
    assert is_critical("desktop_control", "agent")
    # system_monitor status is not critical
    assert not is_critical("system_monitor", "status")
    assert is_critical("system_monitor", "governor")
