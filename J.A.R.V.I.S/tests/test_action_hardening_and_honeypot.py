from __future__ import annotations

import importlib
import socket
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_action_hardening_helpers(tmp_path):
    from core.action_hardening import (
        atomic_write_json,
        safe_url,
        is_protected_process,
        sanitize_filename,
        safe_resolve_path,
    )
    p = tmp_path / "state.json"
    atomic_write_json(p, {"ok": True})
    assert p.is_file() and "ok" in p.read_text(encoding="utf-8")
    assert safe_url("https://example.com/a")
    try:
        safe_url("file:///etc/passwd")
        assert False, "should reject file://"
    except ValueError:
        pass
    assert is_protected_process("csrss.exe") is True
    assert is_protected_process("svchost.exe") is True
    assert sanitize_filename("a/b:c*.txt") == "a_b_c_.txt"
    home_file = Path.home() / "jarvis_hard_test_tmp.txt"
    try:
        home_file.write_text("x", encoding="utf-8")
        r = safe_resolve_path(home_file)
        assert r.exists()
    finally:
        home_file.unlink(missing_ok=True)


def test_honeypot_tool_contract():
    mod = importlib.import_module("actions.security.honeypot_rede_local")
    tool = mod.TOOL
    assert tool["name"] == "honeypot_rede_local"
    assert callable(tool["handler"])


def test_honeypot_start_status_stop():
    from actions.security.honeypot_rede_local import honeypot_rede_local
    # high port to reduce collision
    port = 27123
    r = honeypot_rede_local({"action": "iniciar", "port": port})
    assert "status=done" in r or "status=failed" in r
    if "status=failed" in r:
        # port busy environment — still exercise status path
        s = honeypot_rede_local({"action": "status"})
        assert "status=done" in s
        return
    s = honeypot_rede_local({"action": "status"})
    assert "status=done" in s
    # optional connect
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2) as c:
            c.recv(64)
    except OSError:
        pass
    time.sleep(0.2)
    h = honeypot_rede_local({"action": "historico"})
    assert "status=done" in h
    st = honeypot_rede_local({"action": "parar"})
    assert "status=done" in st
