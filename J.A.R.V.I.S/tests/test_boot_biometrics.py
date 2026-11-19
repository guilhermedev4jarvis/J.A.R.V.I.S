"""Boot uses master password mode — no face/voice gate at startup."""
from __future__ import annotations

from core import boot_biometrics as bb
from core import owner_gate as og


def test_enforce_startup_always_true():
    assert bb.enforce_startup_biometrics() is True


def test_master_password_default():
    assert bb.master_password() == "123gui834"
    assert bb.password_ok("123gui834")
    assert not bb.password_ok("wrong")


def test_owner_gate_password():
    r = og.require_owner(tool_name="test", action="cmd", password="123gui834")
    assert r.get("ok") is True
    r2 = og.require_owner(tool_name="test", action="cmd", password="nope")
    assert r2.get("ok") is False


def test_extract_password():
    assert og.extract_password_from_text("senha 123gui834") == "123gui834"
    assert og.extract_password_from_text("/senha 123gui834") == "123gui834"
