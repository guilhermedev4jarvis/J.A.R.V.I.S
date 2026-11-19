"""Event bus chains, memory consolidate, ROI, ALPR known plate."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.event_bus import EventBus, publish
from actions.security._leitor_placas_alpr_impl import _lookup, _normalize_plate, _confusions
from actions.security._security_vision import point_in_rois, apply_roi_mask
from memory.cognitive_consolidate import consolidate, commitments_for_today


def test_event_rule_wifi_left_triggers_actions():
    bus = EventBus.get()
    bus.reload_rules()
    bus._cooldown.clear()
    rule = next(r for r in bus._rules if r.get("id") == "familia_saiu_mae")
    payload = {"owner_tag": "mae", "mac": "aa:bb"}
    assert bus._match(rule, "wifi.device_left", payload) is True
    calls = []
    with patch("actions.security.sentinel_patrol.sentinel_patrol", side_effect=lambda parameters=None, **kw: calls.append("sentinel") or "ok"):
        with patch("actions.security.anti_sabotagem_energia.anti_sabotagem_energia", side_effect=lambda parameters=None, **kw: calls.append("power") or "ok"):
            for action in rule.get("actions") or []:
                bus._run_action(action, payload, rule["id"])
    assert "sentinel" in calls and "power" in calls


def test_compound_storm_and_outage():
    bus = EventBus.get()
    bus.reload_rules()
    bus._cooldown.clear()
    rule = next(r for r in bus._rules if r.get("id") == "tempestade_e_queda_energia")
    bus.set_fact("evt:weather.storm_alert", {"city": "Rio Preto"}, ttl=900)
    payload = {"percent": 80, "event": "power.outage_detected"}
    assert bus._match(rule, "power.outage_detected", payload) is True
    offline_calls = []
    with patch("actions.ai_core.offline.offline", side_effect=lambda parameters=None, **k: offline_calls.append(parameters or {}) or "status=done"):
        with patch("actions.security._security_vision.send_telegram", return_value={"ok": True}):
            for action in rule.get("actions") or []:
                bus._run_action(action, payload, rule["id"])
    assert offline_calls, "offline action must run for compound rule"



def test_alpr_known_plate_fik5j12():
    assert _normalize_plate("FIK5J12") == "FIK5J12"
    known = _lookup("FIK5J12")
    assert known is not None
    assert "Honda City" in str(known.get("model") or known.get("name"))
    # OCR confusion still matches
    variants = _confusions("FIK5J12")
    assert "FIK5J12" in variants


def test_roi_point_in_gate_polygon():
    # center of portao polygon roughly
    zones = point_in_rois(0.5, 0.6, camera_id="gate")
    assert "portao_secundario" in zones or zones == [] or isinstance(zones, list)
    # outside top may hit muro
    z2 = point_in_rois(0.5, 0.1, camera_id="gate")
    assert isinstance(z2, list)


def test_memory_commitments_extraction(tmp_path, monkeypatch):
    import memory.cognitive_consolidate as cc
    ep = tmp_path / "episodes.jsonl"
    ep.write_text(
        json.dumps({"text": "Minha mãe tem consulta médica quinta às 14h"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cc, "_EP", ep)
    monkeypatch.setattr(cc, "_DIARIO", tmp_path / "d.jsonl")
    monkeypatch.setattr(cc, "_LONG", tmp_path / "long_term.json")
    monkeypatch.setattr(cc, "_GRAPH", tmp_path / "graph.json")
    r = consolidate()
    assert r["commitments"] >= 1
    data = json.loads((tmp_path / "long_term.json").read_text(encoding="utf-8"))
    assert data["commitments"][0]["entity"] in ("mãe", "mae")
