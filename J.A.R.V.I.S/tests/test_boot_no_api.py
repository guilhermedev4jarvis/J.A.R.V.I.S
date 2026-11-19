"""Boot / access smoke tests — no Gemini, no network, no API key."""
from __future__ import annotations

import os

import pytest

# Force offline-safe env for this module
os.environ.setdefault("JARVIS_SKIP_PREBOOT", "1")
os.environ.setdefault("JARVIS_SKIP_FACE_BOOT", "1")
os.environ.setdefault("JARVIS_SKIP_CAMERA", "1")
os.environ.setdefault("JARVIS_SKIP_VSM_LAUNCH", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_preboot_password_hash():
    from core.preboot_gate import password_ok, expected_hash, DEFAULT_PLAIN, DEFAULT_HASH
    assert DEFAULT_PLAIN == "123gui834"
    assert len(expected_hash()) == 64
    assert password_ok("123gui834") is True
    assert password_ok("errada") is False
    assert password_ok("") is False
    assert password_ok(None) is False


def test_preboot_skip_env():
    from core import preboot_gate as pg
    # reset and skip
    pg._validated = False
    os.environ["JARVIS_SKIP_PREBOOT"] = "1"
    assert pg.run_preboot_gate(force=True) is True
    assert pg.is_validated() is True


def test_boot_biometrics_skip():
    from core.boot_biometrics import enforce_startup_biometrics, master_password, password_ok
    os.environ["JARVIS_SKIP_FACE_BOOT"] = "1"
    assert master_password() == "123gui834"
    assert password_ok("123gui834") is True
    assert enforce_startup_biometrics() is True


def test_owner_gate_password():
    from core import owner_gate as og
    r = og.require_owner(tool_name="test", action="cmd", password="123gui834")
    assert r.get("ok") is True
    r2 = og.require_owner(tool_name="test", action="cmd", password="nope")
    assert r2.get("ok") is False


def test_vsm_health_no_exe():
    from core.vsm_health import run_health_check, candidate_paths
    report = run_health_check(try_launch=False)
    assert "ok" in report
    assert "message" in report
    assert isinstance(report["ok"], bool)
    paths = candidate_paths()
    assert any("VSM" in str(p) for p in paths)


def test_redaction_masks_password():
    from core.redaction import redact_text
    out = redact_text("password=123gui834 used at boot")
    assert "123gui834" not in out
    assert "***" in out


def test_import_core_without_gemini_live():
    """Heavy modules import; do not open Live session."""
    import core.secrets
    import core.audit
    import core.outcome
    import core.contracts
    assert core.secrets is not None


def test_action_loader_discovers_or_empty():
    """Discovery may be 0 in some layouts; must not crash."""
    from pathlib import Path
    from core import action_loader
    actions_dir = Path(__file__).resolve().parents[1] / "actions"
    if hasattr(action_loader, "discover_actions"):
        try:
            d = action_loader.discover_actions(actions_dir)
        except TypeError:
            d = action_loader.discover_actions()
        assert d is not None
    elif hasattr(action_loader, "load_all_actions"):
        d = action_loader.load_all_actions()
        assert d is not None
    else:
        pytest.skip("no discover API")
