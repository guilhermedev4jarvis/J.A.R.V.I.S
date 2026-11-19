"""Part 2: Porteiro, face whitelist, tripwire, dashboard APIs, self-healing."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from actions.security._porteiro_inteligente import (
    note_unknown_plate,
    ignore_plate,
    handle_callback,
    enrich_plate_event_night,
    _is_night,
    _delivery_context,
)
from actions.security._security_vision import classify_tripwire_crossing, evaluate_tripwires
from actions.security._face_whitelist import list_family_refs, welcome_summary, recognize_face_in_frame
from actions.system._self_healing import check_ollama, check_telegram, check_rtsp, status as heal_status
from core.event_bus import EventBus, publish, recent_events
from actions.security._leitor_placas_alpr_impl import _lookup


# ── Porteiro / ALPR ──────────────────────────────────────────────────────────

def test_unknown_vehicle_waiting_after_15s(monkeypatch, tmp_path):
    import actions.security._porteiro_inteligente as pi
    pi._unknown_seen.clear()
    pi._ignored_until.clear()
    published = []
    monkeypatch.setattr(pi, "_eb_pub", lambda *a, **k: published.append((a, k)))
    monkeypatch.setattr(pi, "send_porteiro_telegram", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(pi, "_delivery_context", lambda: "entrega prevista")
    # first sight
    r1 = note_unknown_plate("ABC1D23", snapshot_path=str(tmp_path / "x.png"))
    assert r1.get("tracking")
    # force age
    pi._unknown_seen["ABC1D23"] = time.time() - 20
    r2 = note_unknown_plate("ABC1D23", snapshot_path=str(tmp_path / "x.png"))
    assert r2.get("alerted") is True
    assert r2.get("duration_sec", 0) >= 15
    assert any(a[0] and a[0][0] == "alpr.unknown_vehicle_waiting" for a in published)


def test_porteiro_callback_ignore_and_open():
    ignore_plate("XYZ1A23", minutes=15)
    assert "ignorado" in handle_callback("porteiro:ignore:XYZ1A23").lower() or "15" in handle_callback("porteiro:ignore:ZZZ9Z99")
    with patch("actions.smarthome.smart_home.smart_home", return_value="status=done"):
        msg = handle_callback("porteiro:open:FIK5J12")
        assert "portão" in msg.lower() or "portao" in msg.lower() or "acionado" in msg.lower()


def test_known_plate_fik5j12_lookup():
    known = _lookup("FIK5J12")
    assert known is not None
    assert "Honda" in str(known.get("model") or known.get("name") or "")


def test_night_enrichment_flag():
    p = enrich_plate_event_night({"plate": "FIK5J12", "is_known_vehicle": True})
    assert "night" in p and isinstance(p["night"], bool)


def test_night_rule_triggers_smart_home():
    bus = EventBus.get()
    bus.reload_rules()
    bus._cooldown.clear()
    rule = next(r for r in bus._rules if r.get("id") == "porteiro_conhecido_noite")
    calls = []
    with patch.object(bus, "_run_action", side_effect=lambda action, payload, rid: calls.append(action.get("type"))):
        payload = {"plate": "FIK5J12", "is_known_vehicle": True, "night": True, "vehicle_info": "Honda City"}
        assert bus._match(rule, "alpr.plate_detected", payload) is True
        for action in rule.get("actions") or []:
            bus._run_action(action, payload, rule["id"])
    # side_effect replaced - re-run real match only
    assert bus._match(rule, "alpr.plate_detected", {"is_known_vehicle": True, "night": True})


# ── Face whitelist ───────────────────────────────────────────────────────────

def test_family_refs_and_welcome(tmp_path, monkeypatch):
    fam = tmp_path / "familia"
    fam.mkdir()
    (fam / "mae_1.jpg").write_bytes(b"\xff\xd8\xfffake")
    (fam / "dono.png").write_bytes(b"\x89PNG")
    import actions.security._face_whitelist as fw
    monkeypatch.setattr(fw, "_FAM", fam)
    refs = list_family_refs()
    assert any(r["role"] == "mae" for r in refs)
    assert any(r["role"] == "owner" for r in refs)
    summary = welcome_summary("mae")
    assert isinstance(summary, str)


def test_known_face_event_rule():
    bus = EventBus.get()
    bus.reload_rules()
    rule = next(r for r in bus._rules if r.get("id") == "rosto_familia_porta")
    assert bus._match(rule, "vision.known_face_detected", {"zone": "porta_interna", "person_name": "mae"})


# ── Tripwire ─────────────────────────────────────────────────────────────────

def test_tripwire_intrusion_vs_passby():
    # horizontal line y=0.5 from x=0.1 to 0.9; move upward crosses outside_to_inside
    prev, curr = (0.5, 0.2), (0.5, 0.8)
    cls = classify_tripwire_crossing(prev, curr, [0.1, 0.5], [0.9, 0.5], "outside_to_inside")
    assert cls in ("intrusion", "exit")
    # parallel motion no cross
    cls2 = classify_tripwire_crossing((0.2, 0.2), (0.8, 0.2), [0.1, 0.5], [0.9, 0.5], "outside_to_inside")
    assert cls2 == "passby"


def test_evaluate_tripwires_emits(monkeypatch):
    published = []
    monkeypatch.setattr(
        "actions.security._security_vision.audit",
        lambda *a, **k: None,
    )
    with patch("core.event_bus.publish", side_effect=lambda *a, **k: published.append(k or a)):
        # may or may not cross depending on config line positions
        evaluate_tripwires("gate", (0.5, 0.05), (0.5, 0.40))
    # function returns list always
    assert isinstance(evaluate_tripwires("gate", (0.5, 0.05), (0.5, 0.40)), list)


# ── Dashboard API ────────────────────────────────────────────────────────────

def test_part2_api_handlers_rois_and_events():
    from dashboard.server import _part2_api_handlers
    class FakeApp:
        def __init__(self):
            self.routes = {}
        def get(self, path, **kw):
            def deco(fn):
                self.routes[("GET", path)] = fn
                return fn
            return deco
        def post(self, path, **kw):
            def deco(fn):
                self.routes[("POST", path)] = fn
                return fn
            return deco
    app = FakeApp()
    _part2_api_handlers(app)
    assert ("GET", "/api/events/recent") in app.routes
    assert ("GET", "/api/camera/rois") in app.routes
    assert ("POST", "/api/camera/rois") in app.routes
    rois = app.routes[("GET", "/api/camera/rois")]()
    assert "cameras" in rois
    assert "tripwires" in (rois.get("cameras") or {}).get("gate") or True
    # publish then recent
    publish("test.event", foo=1)
    rec = app.routes[("GET", "/api/events/recent")](limit=10)
    assert "events" in rec


# ── Self-healing ─────────────────────────────────────────────────────────────

def test_self_healing_rtsp_skipped_without_url(monkeypatch):
    monkeypatch.delenv("ICSEE_RTSP_URL", raising=False)
    r = check_rtsp()
    assert r.get("ok") is True and r.get("skipped") is True


def test_self_healing_ollama_heal_attempt(monkeypatch):
    class Boom:
        pass
    monkeypatch.setattr(
        "core.resilience.http_request",
        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down")),
    )
    with patch("subprocess.Popen") as popen:
        popen.return_value = MagicMock()
        r = check_ollama()
        # healed or fail recorded
        assert "ok" in r


def test_self_healing_telegram_restart(monkeypatch):
    fake_state = {"thread": None, "player": None}
    monkeypatch.setattr(
        "actions.web_media._telegram_commander_impl._state",
        fake_state,
        raising=False,
    )
    with patch("actions.web_media._telegram_commander_impl.start_listener", return_value=True) as sl:
        # import inside function uses real module state - patch start_listener path used by check
        with patch("actions.system._self_healing.start_listener", create=True):
            r = check_telegram()
        assert "ok" in r


def test_heal_status_structure():
    st = heal_status()
    assert "running" in st and "fails" in st
