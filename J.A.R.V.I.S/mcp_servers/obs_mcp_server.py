#!/usr/bin/env python3
"""OBS Studio MCP server — obs-websocket v5 (graceful if OBS is closed)."""
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

# allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_servers._mcp_stdio import serve  # noqa: E402


def _ws_request(request_type: str, request_data: dict | None = None) -> dict:
    host = os.getenv("OBS_WS_HOST") or "127.0.0.1"
    port = int(os.getenv("OBS_WS_PORT") or "4455")
    password = os.getenv("OBS_WS_PASSWORD") or ""
    # Lightweight TCP probe + optional websocket if library available
    try:
        sock = socket.create_connection((host, port), timeout=2.0)
        sock.close()
    except OSError as e:
        return {
            "ok": False,
            "error": "obs_unreachable",
            "detail": f"OBS websocket {host}:{port} indisponível ({e}). Abra o OBS Studio e ative obs-websocket v5.",
        }
    try:
        import websocket  # type: ignore

        ws = websocket.create_connection(f"ws://{host}:{port}", timeout=3)
        try:
            hello = json.loads(ws.recv())
            # Identify (no auth or with password if required)
            identify = {
                "op": 1,
                "d": {
                    "rpcVersion": 1,
                    "eventSubscriptions": 0,
                },
            }
            if password and hello.get("d", {}).get("authentication"):
                # simplified: send password field if present (full auth needs challenge hash)
                identify["d"]["authentication"] = password
            ws.send(json.dumps(identify))
            _ = ws.recv()
            req = {
                "op": 6,
                "d": {
                    "requestType": request_type,
                    "requestId": "jarvis-1",
                    "requestData": request_data or {},
                },
            }
            ws.send(json.dumps(req))
            resp = json.loads(ws.recv())
            return {"ok": True, "response": resp}
        finally:
            ws.close()
    except ImportError:
        return {
            "ok": True,
            "mode": "probe_only",
            "message": f"OBS porta {port} aberta. Instale o pacote 'websocket-client' para controle completo.",
            "request": request_type,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "request": request_type}


TOOLS = {
    "obs_get_status": {
        "description": "Status do OBS (versão/stream/record se disponível).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "obs_switch_scene": {
        "description": "Troca a cena atual do OBS.",
        "inputSchema": {
            "type": "object",
            "properties": {"scene_name": {"type": "string"}},
            "required": ["scene_name"],
        },
    },
    "obs_start_recording": {
        "description": "Inicia gravação no OBS.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "obs_stop_recording": {
        "description": "Para gravação no OBS.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "obs_save_replay_buffer": {
        "description": "Salva o replay buffer do OBS.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "obs_toggle_mute": {
        "description": "Alterna mute de uma fonte de áudio.",
        "inputSchema": {
            "type": "object",
            "properties": {"input_name": {"type": "string"}},
            "required": ["input_name"],
        },
    },
}


def main() -> None:
    handlers = {
        "obs_get_status": lambda a: _ws_request("GetStats"),
        "obs_switch_scene": lambda a: _ws_request(
            "SetCurrentProgramScene", {"sceneName": a.get("scene_name") or a.get("sceneName")}
        ),
        "obs_start_recording": lambda a: _ws_request("StartRecord"),
        "obs_stop_recording": lambda a: _ws_request("StopRecord"),
        "obs_save_replay_buffer": lambda a: _ws_request("SaveReplayBuffer"),
        "obs_toggle_mute": lambda a: _ws_request(
            "ToggleInputMute", {"inputName": a.get("input_name") or a.get("inputName")}
        ),
    }
    serve(TOOLS, handlers)


if __name__ == "__main__":
    main()
