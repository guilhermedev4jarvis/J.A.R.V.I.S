"""Deep stress & coverage — EventBus, knowledge FTS/BM25, vision, finance, dashboard, healing."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


# ── Knowledge store ──────────────────────────────────────────────────────────

def test_knowledge_reindex_and_search():
    from core import knowledge_store as ks
    stats = ks.reindex_all(ROOT / "memory" / "knowledge_docs")
    assert stats["files"] >= 1
    hits = ks.search("protocolo 190 silencioso", limit=5)
    assert hits, "expected FTS/BM25 hits for protocolo 190"
    ans = ks.answer_with_citations("Honda City manutenção óleo")
    assert ans.get("ok") in (True, False) or "answer" in ans or hits
    assert ans.get("citations")


def test_knowledge_bm25_empty_query():
    from core import knowledge_store as ks
    assert ks.search("") == []


def test_knowledge_chunking_overlap():
    from core.knowledge_store import chunk_text
    chunks = chunk_text("a" * 2000, size=500, overlap=100)
    assert len(chunks) >= 4


def test_knowledge_cache_hits():
    from core import knowledge_store as ks
    ks.reindex_all(ROOT / "memory" / "knowledge_docs")
    a = ks.search("emergência residencial", limit=3)
    b = ks.search("emergência residencial", limit=3)
    assert a == b


# ── EventBus stress ──────────────────────────────────────────────────────────

def test_event_bus_many_events_and_history():
    from core.event_bus import EventBus, publish, recent_events
    bus = EventBus.get()
    bus._cooldown.clear()
    for i in range(120):
        publish(f"stress.event_{i % 7}", n=i)
    hist = recent_events(80)
    assert len(hist) >= 50


def test_event_bus_sliding_window():
    from core.event_bus import EventBus, publish
    bus = EventBus.get()
    bus._cooldown.clear()
    for _ in range(3):
        publish("power.outage_detected", percent=50)
    assert bus.sliding_window_count("power.outage_detected", 60) >= 3
    when = {"slide": {"event": "power.outage_detected", "count": 2, "window_sec": 120}}
    assert bus.match_sliding("power.outage_detected", {}, when) is True


def test_event_bus_persist_and_load(tmp_path, monkeypatch):
    from core.event_bus import EventBus, publish
    bus = EventBus.get()
    path = tmp_path / "event_bus_state.json"
    publish("persist.test", x=1)
    bus.persist_state(path)
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "history_tail" in data


def test_event_bus_rules_count_ge_20():
    data = json.loads((ROOT / "config" / "event_rules.json").read_text(encoding="utf-8"))
    assert len(data.get("rules") or []) >= 20


def test_event_bus_concurrent_publish():
    from core.event_bus import publish, recent_events
    def worker(n):
        for i in range(20):
            publish("concurrent.pulse", worker=n, i=i)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert any(e.get("event") == "concurrent.pulse" for e in recent_events(100))


def test_event_bus_dlq_on_bad_action():
    from core.event_bus import EventBus
    bus = EventBus.get()
    bus._run_action({"type": "tool_that_does_not_exist_xyz"}, {}, "test_dlq")
    assert any(d.get("rule") == "test_dlq" for d in getattr(bus, "_dlq", []))


# ── Vision / tripwire / motion ───────────────────────────────────────────────

def test_tripwire_matrix_angles():
    from actions.security._security_vision import classify_tripwire_crossing
    # vertical-ish motion across horizontal line
    assert classify_tripwire_crossing((0.5, 0.1), (0.5, 0.9), [0.0, 0.5], [1.0, 0.5]) in ("intrusion", "exit")
    assert classify_tripwire_crossing((0.1, 0.1), (0.9, 0.1), [0.0, 0.5], [1.0, 0.5]) == "passby"
    assert classify_tripwire_crossing((0.2, 0.8), (0.2, 0.2), [0.0, 0.5], [1.0, 0.5]) in ("intrusion", "exit")


def test_object_tracker_ids_stable():
    from actions.security._security_vision import ObjectTracker
    tr = ObjectTracker(max_dist=0.2)
    a = tr.update([(0.1, 0.1), (0.8, 0.8)])
    b = tr.update([(0.12, 0.11), (0.79, 0.81)])
    assert len(a) == 2 and len(b) == 2


def test_motion_subtractor_and_morph():
    import numpy as np
    from actions.security._security_vision import MotionSubtractor, morphological_clean, centroids_from_mask
    ms = MotionSubtractor()
    frame = np.zeros((60, 80, 3), dtype="uint8")
    mask = ms.apply(frame)
    mask2 = ms.apply(frame + 40)
    cleaned = morphological_clean(mask2)
    assert cleaned is not None


def test_lbp_histogram_similarity():
    import numpy as np
    from actions.security._security_vision import lbp_histogram, hist_similarity
    img = np.random.randint(0, 255, (32, 32), dtype="uint8")
    h1 = lbp_histogram(img)
    h2 = lbp_histogram(img)
    assert len(h1) == 16
    assert hist_similarity(h1, h2) > 0.9


def test_roi_point_gate_zones():
    from actions.security._security_vision import point_in_rois
    z = point_in_rois(0.5, 0.6, "gate")
    assert isinstance(z, list)


# ── Finance ──────────────────────────────────────────────────────────────────

def test_finance_ema_recurring_projection(tmp_path, monkeypatch):
    import actions.finance_shopping._finance_audit as fa
    csv_path = tmp_path / "gastos.csv"
    lines = ["data,descricao,categoria,valor\n"]
    for i in range(1, 10):
        lines.append(f"2026-11-{i:02d},NETFLIX STREAMING,lazer,45.90\n")
    for i in range(1, 8):
        lines.append(f"2026-11-{i:02d},IFOOD DELIVERY,delivery,{50+i}.00\n")
    csv_path.write_text("".join(lines), encoding="utf-8")
    monkeypatch.setattr(fa, "_GASTOS", csv_path)
    ema = fa.exponential_moving_average([10, 12, 14, 13, 20])
    assert len(ema) == 5
    rec = fa.detect_recurring_charges(min_count=3, amount_tol=1.0)
    assert any("netflix" in r["description"] for r in rec)
    proj = fa.month_end_projection()
    assert "projected_month_end" in proj
    md = fa.finance_report_markdown()
    assert "Relatório" in md or "Projeção" in md


# ── Porteiro / presence / climate ────────────────────────────────────────────

def test_porteiro_ignore_and_tracking(tmp_path, monkeypatch):
    import actions.security._porteiro_inteligente as pi
    pi._unknown_seen.clear()
    pi._ignored_until.clear()
    monkeypatch.setattr(pi, "send_porteiro_telegram", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(pi, "_eb_pub", lambda *a, **k: None)
    r = pi.note_unknown_plate("TST1A23")
    assert r.get("tracking")
    pi.ignore_plate("TST1A23", 15)
    r2 = pi.note_unknown_plate("TST1A23")
    assert r2.get("ignored")


def test_presence_resident_tags():
    from actions.ai_core._presence_travel import is_resident_tag, residents_present
    assert is_resident_tag("mae")
    assert is_resident_tag("owner")
    assert not is_resident_tag("vizinho")
    known = {"aa:11": "owner"}
    assert residents_present([{"mac": "aa:11"}], known) == ["owner"]


def test_smart_climate_thresholds(monkeypatch):
    import actions.smarthome._smart_climate as sc
    monkeypatch.setattr(sc, "_temp_c", lambda: 10.0)
    called = []
    monkeypatch.setattr(sc, "_activate_climate", lambda r, t: called.append(t) or {"ok": True})
    sc.on_trusted_vehicle_arrival("FIK5J12", True)
    assert called and called[0] == 10.0


# ── Continuous listen / offline knowledge ────────────────────────────────────

def test_continuous_listen_states():
    from core import continuous_listen as cl
    cl.close_followup()
    cl.on_tts_finished()
    assert cl.should_accept_without_wake("status do sistema")
    cl.close_followup()


def test_offline_knowledge_answer():
    from actions.ai_core._offline_impl import offline_knowledge_answer
    r = offline_knowledge_answer("protocolo de emergência 190")
    assert "ok" in r


# ── Dashboard routes registry ────────────────────────────────────────────────

def test_dashboard_part2_routes_register():
    from dashboard.server import _part2_api_handlers
    class App:
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
    app = App()
    _part2_api_handlers(app)
    for path in ("/api/events/recent", "/api/camera/rois", "/api/alpr/last"):
        assert ("GET", path) in app.routes


# ── Self healing ─────────────────────────────────────────────────────────────

def test_self_healing_status_and_rtsp_skip(monkeypatch):
    from actions.system._self_healing import status, check_rtsp
    monkeypatch.delenv("ICSEE_RTSP_URL", raising=False)
    assert check_rtsp().get("skipped") is True
    assert "fails" in status()


# ── Action contracts smoke ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    "mod_name",
    [
        "actions.productivity.mover_downloads",
        "actions.ai_core.offline",
        "actions.productivity.protocolo",
        "actions.ai_core.mcp_manager",
        "actions.security.leitor_placas_alpr",
    ],
)
def test_action_module_has_tool(mod_name):
    import importlib
    mod = importlib.import_module(mod_name)
    assert hasattr(mod, "TOOL")
    assert mod.TOOL.get("name")
    assert callable(mod.TOOL.get("handler"))


# ── Stress cascade rules without infinite loop ───────────────────────────────

def test_rule_cooldown_prevents_tight_loop():
    from core.event_bus import EventBus
    bus = EventBus.get()
    bus._cooldown.clear()
    rid = "cooldown_test_rule"
    first = bus._cooldown_ok(rid, 30)
    second = bus._cooldown_ok(rid, 30)
    # First call may arm cooldown; second should block if implementation tracks it.
    assert first in (True, False)
    assert second in (True, False)
    if first is True:
        assert second is False


def test_known_vehicles_and_docs_exist():
    assert (ROOT / "config" / "known_vehicles.json").is_file()
    assert (ROOT / "README.md").is_file()
    assert (ROOT / "memory" / "knowledge_docs").is_dir()
    kv = json.loads((ROOT / "config" / "known_vehicles.json").read_text(encoding="utf-8"))
    assert any(v.get("plate") == "FIK5J12" for v in kv.get("vehicles") or [])


# Generate additional parameterized stress for bus event names
@pytest.mark.parametrize("ev", [f"metric.tick_{i}" for i in range(15)])
def test_publish_metric_ticks(ev):
    from core.event_bus import publish
    publish(ev, ok=True)


@pytest.mark.parametrize(
    "q",
    [
        "primeiro socorros queimadura",
        "Ollama offline",
        "tripwire invasão",
        "modo viagem 6 horas",
        "ALPR FIK5J12",
        "backup memória",
        "WPA3 rede",
        "filtro ar-condicionado",
        "SAMU 192",
        "extintor incêndio",
    ],
)
def test_knowledge_queries_varied(q):
    from core import knowledge_store as ks
    # reindex once is enough; search may return empty for some but must not raise
    ks.search(q, limit=3)


def test_local_doc_rag_search_path():
    import actions.ai_core.local_doc_rag as local_doc_rag
    r = local_doc_rag.local_doc_rag({"action": "search", "query": "protocolo 190"})
    assert "status=" in r
