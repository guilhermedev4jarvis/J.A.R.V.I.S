"""Implementacao do detector de encomendas no portao com integracao ROI e alertas."""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from core.outcome import done, started

_BASE = Path(__file__).resolve().parents[2]
_ROIS_PATH = _BASE / "config" / "camera_rois.json"
_AUDIT_DIR = _BASE / "memory" / "audit"
_state: Dict[str, Any] = {"active": False, "stop": None, "last_alert": None, "detections": 0}
_lock = threading.Lock()


def _load_roi(roi_name: str) -> Dict[str, Any]:
    if _ROIS_PATH.exists():
        try:
            data = json.loads(_ROIS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data.get(roi_name) or data.get("rois", {}).get(roi_name) or {}
        except Exception:
            pass
    return {}


def _notify_delivery(summary: str, image_path: str | None = None) -> list[str]:
    channels = []
    try:
        from actions.web_media._telegram_commander_impl import send_alert
        send_alert(summary, photo_path=image_path)
        channels.append("telegram")
    except Exception:
        pass
    try:
        from actions.web_media.whatsapp_web import whatsapp_web
        whatsapp_web({"action": "send", "message": summary})
        channels.append("whatsapp")
    except Exception:
        pass
    return channels


def _inspect_gate_frame(roi_name: str) -> Dict[str, Any]:
    roi = _load_roi(roi_name)
    _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    snap_path = None
    package_found = False
    try:
        from actions.security import _security_vision as sv
        if hasattr(sv, "detect_stationary_objects"):
            res = sv.detect_stationary_objects(roi=roi)
            package_found = bool(res.get("detected"))
            snap_path = res.get("snapshot_path")
    except Exception:
        pass
    return {"roi_name": roi_name, "roi_configured": bool(roi), "package_detected": package_found, "snapshot": snap_path}


def _worker(stop_evt: threading.Event, roi_name: str, dwell: float) -> None:
    while not stop_evt.is_set():
        info = _inspect_gate_frame(roi_name)
        if info["package_detected"]:
            with _lock:
                _state["detections"] += 1
                _state["last_alert"] = datetime.now().isoformat()
            channels = _notify_delivery(f"Encomenda detectada na area '{roi_name}'.", info.get("snapshot"))
            try:
                from core import audit
                audit.log_event("delivery_detected", {**info, "channels": channels})
            except Exception:
                pass
            stop_evt.wait(max(30.0, dwell * 3))
        else:
            stop_evt.wait(max(3.0, dwell))


def run(parameters=None, player=None, session_memory=None, **ctx):
    params = parameters or {}
    action = str(params.get("action") or "status").lower()
    roi_name = str(params.get("roi_name") or "portao")
    dwell = float(params.get("dwell_seconds") or 12)

    if action == "start":
        with _lock:
            if _state["active"]:
                return done("detector_encomendas_portao", "Detector de encomendas ja esta ativo.", {"active": True})
            stop_evt = threading.Event()
            t = threading.Thread(target=_worker, args=(stop_evt, roi_name, dwell), daemon=True)
            _state["active"] = True
            _state["stop"] = stop_evt
            t.start()
        return started("detector_encomendas_portao", f"Monitoramento de encomendas iniciado na ROI '{roi_name}'.", {"roi": roi_name})

    if action == "stop":
        with _lock:
            if _state["stop"]:
                _state["stop"].set()
            _state["active"] = False
            _state["stop"] = None
        return done("detector_encomendas_portao", "Detector de encomendas encerrado.", {"active": False})

    if action == "check_now":
        info = _inspect_gate_frame(roi_name)
        return done("detector_encomendas_portao", "Verificacao pontual concluida.", info)

    with _lock:
        snapshot = {"active": _state["active"], "detections": _state["detections"], "last_alert": _state["last_alert"]}
    return done("detector_encomendas_portao", "Status do detector de encomendas.", snapshot)