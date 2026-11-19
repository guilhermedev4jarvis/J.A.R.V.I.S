"""Resilience: timeouts, atomic JSON, offline HTTP, password/protocol invariants."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.resilience import (
    atomic_write_json,
    http_request,
    safe_read_json,
    sanitize_phone,
    sanitize_plate,
)
from core.boot_biometrics import password_ok
from core.retry import retry_call


def test_sanitize_helpers():
    assert sanitize_phone("+55 (17) 99999-9999") == "5517999999999"
    assert sanitize_plate("abc-1d23") == "ABC1D23"
    assert password_ok("123gui834")


def test_atomic_json_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    atomic_write_json(path, {"ok": True, "n": 1})
    data = safe_read_json(path)
    assert data["ok"] is True and data["n"] == 1


def test_safe_read_corrupt_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    assert safe_read_json(path, default={"vehicles": {}}) == {"vehicles": {}}


def test_retry_call_eventually_succeeds():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("blip")
        return "ok"

    assert retry_call(flaky, attempts=4, base_delay=0.01, max_delay=0.02) == "ok"
    assert calls["n"] == 3


def test_http_request_offline_fallback():
    def offline(e):
        return "OFFLINE"

    with patch("requests.request", side_effect=ConnectionError("down")):
        out = http_request(
            "GET",
            "https://example.invalid/x",
            timeout=(0.2, 0.2),
            attempts=2,
            offline_result=offline,
        )
    assert out == "OFFLINE"


def test_protocolo_190_no_password_gate(monkeypatch):
    import actions.productivity._protocolo_impl as impl
    monkeypatch.setattr(impl, "capture_with_fallbacks", lambda **kw: {"ok": False, "reason": "test"})
    monkeypatch.setattr(impl, "send_telegram", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(impl, "send_whatsapp", lambda *a, **k: {"ok": True})
    import actions.productivity.protocolo as protocolo
    r = protocolo.protocolo({"action": "ativar", "nome": "190"})
    assert "190" in r
    assert "status=done" in r or "status=failed" in r


def test_capture_with_fallbacks_exists():
    from actions.security._security_vision import capture_with_fallbacks
    assert callable(capture_with_fallbacks)


def test_radar_offline_message():
    from actions.web_media._radar_climatico_rp_impl import check_and_notify
    with patch("actions.web_media._radar_climatico_rp_impl._forecast", side_effect=ConnectionError("net")):
        r = check_and_notify(player=None, force_voice=False)
    assert r.get("ok") is False
    assert r.get("offline") is True or "rede" in str(r.get("reason") or "").lower() or "net" in str(r.get("detail") or "").lower()
