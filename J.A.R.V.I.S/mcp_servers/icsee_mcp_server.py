#!/usr/bin/env python3
"""iCSee cameras MCP server — ROIs, snapshots, stream health, alerts."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_servers._mcp_stdio import serve  # noqa: E402

_BASE = Path(__file__).resolve().parents[1]


def _cfg_path() -> Path:
    raw = os.getenv("ICSEE_CONFIG_PATH") or "config/camera_rois.json"
    p = Path(raw)
    if not p.is_absolute():
        p = _BASE / p
    return p


def icsee_list_cameras(_args: dict) -> dict:
    path = _cfg_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)[:160], "cameras": []}
    cams = []
    for key, cfg in (data.get("cameras") or {}).items():
        cams.append(
            {
                "id": cfg.get("camera_id") or key,
                "label": cfg.get("label") or key,
                "polygons": len(cfg.get("polygons") or []),
                "tripwires": len(cfg.get("tripwires") or []),
            }
        )
    return {"ok": True, "cameras": cams}


def icsee_capture_snapshot(args: dict) -> dict:
    camera_id = args.get("camera_id") or "gate"
    try:
        from actions.security._security_vision import capture_with_fallbacks

        cap = capture_with_fallbacks(player=None, load_delay=float(args.get("delay") or 1.0))
        return {
            "ok": bool(cap.get("ok")),
            "camera_id": camera_id,
            "path": cap.get("path"),
            "strategy": cap.get("strategy"),
            "reason": cap.get("reason"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def icsee_get_rois_and_tripwires(_args: dict) -> dict:
    path = _cfg_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def icsee_check_stream_health(_args: dict) -> dict:
    url = (os.getenv("ICSEE_RTSP_URL") or "").strip()
    if not url:
        return {"ok": True, "skipped": True, "reason": "ICSEE_RTSP_URL não configurada"}
    try:
        import cv2

        cap = cv2.VideoCapture(url)
        try:
            ok, frame = cap.read()
            return {"ok": bool(ok and frame is not None), "rtsp": True}
        finally:
            cap.release()
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def icsee_trigger_siren_or_tts(args: dict) -> dict:
    text = args.get("text") or "Atenção. Propriedade monitorada."
    mode = (args.get("mode") or "tts").lower()
    try:
        if mode == "siren":
            try:
                import actions.security.protocolo_dissuasao as protocolo_dissuasao

                return {"ok": True, "result": protocolo_dissuasao.protocolo_dissuasao(parameters={"action": "ativar"})}
            except Exception as e:
                return {"ok": False, "error": str(e)[:160]}
        from actions.security._security_vision import speak_short

        speak_short(text, player=None)
        return {"ok": True, "mode": "tts", "text": text}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


TOOLS = {
    "icsee_list_cameras": {"description": "Lista câmeras/ROIs configuradas.", "inputSchema": {"type": "object", "properties": {}}},
    "icsee_capture_snapshot": {
        "description": "Captura snapshot (iCSee/fallbacks).",
        "inputSchema": {
            "type": "object",
            "properties": {"camera_id": {"type": "string"}, "delay": {"type": "number"}},
        },
    },
    "icsee_get_rois_and_tripwires": {
        "description": "Retorna polígonos ROI e tripwires.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "icsee_check_stream_health": {
        "description": "Testa leitura de frame RTSP se configurado.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "icsee_trigger_siren_or_tts": {
        "description": "Dispara TTS ou modo sirene/dissuasão.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "mode": {"type": "string", "enum": ["tts", "siren"]},
            },
        },
    },
}


def main() -> None:
    serve(
        TOOLS,
        {
            "icsee_list_cameras": icsee_list_cameras,
            "icsee_capture_snapshot": icsee_capture_snapshot,
            "icsee_get_rois_and_tripwires": icsee_get_rois_and_tripwires,
            "icsee_check_stream_health": icsee_check_stream_health,
            "icsee_trigger_siren_or_tts": icsee_trigger_siren_or_tts,
        },
    )


if __name__ == "__main__":
    main()
