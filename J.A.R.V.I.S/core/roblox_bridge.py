"""
core/roblox_bridge.py — localhost HTTP bridge for Roblox Studio plugins.

Studio-side Luau long-polls GET /poll and applies build ops in the editor
(ChangeHistoryService, Parts, CSG when available). JARVIS enqueues via POST /enqueue.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 28859

_lock = threading.Lock()
_queue: list[dict[str, Any]] = []
_history: list[dict[str, Any]] = []
_server: Optional[ThreadingHTTPServer] = None
_thread: Optional[threading.Thread] = None
_host = DEFAULT_HOST
_port = DEFAULT_PORT


def is_running() -> bool:
    return _server is not None and _thread is not None and _thread.is_alive()


def status() -> dict[str, Any]:
    with _lock:
        return {
            "running": is_running(),
            "host": _host,
            "port": _port,
            "queue_len": len(_queue),
            "history_len": len(_history),
            "base_url": f"http://{_host}:{_port}",
        }


def enqueue(op: dict[str, Any]) -> dict[str, Any]:
    """Add a build op. Returns the stored record (with id + ts)."""
    rec = {
        "id": str(uuid.uuid4()),
        "ts": time.time(),
        "op": op,
        "status": "queued",
    }
    with _lock:
        _queue.append(rec)
        _history.append(rec)
        if len(_history) > 200:
            del _history[:-200]
    return rec


def _pop_batch(max_items: int = 8) -> list[dict[str, Any]]:
    with _lock:
        batch = _queue[:max_items]
        del _queue[: len(batch)]
        for rec in batch:
            rec["status"] = "delivered"
        return batch


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # silence default noise
        return

    def _json(self, code: int, payload: Any) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/status"):
            self._json(200, status())
            return
        if path == "/poll":
            # Long-poll up to ~2s for Studio plugin friendliness
            deadline = time.time() + 2.0
            batch: list[dict[str, Any]] = []
            while time.time() < deadline:
                batch = _pop_batch()
                if batch:
                    break
                time.sleep(0.15)
            self._json(200, {"ok": True, "ops": batch})
            return
        if path == "/history":
            with _lock:
                hist = list(_history[-50:])
            self._json(200, {"ok": True, "history": hist})
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            self._json(400, {"ok": False, "error": "invalid_json"})
            return
        if path == "/enqueue":
            op = data.get("op") if isinstance(data.get("op"), dict) else data
            if not isinstance(op, dict) or not op.get("type"):
                self._json(400, {"ok": False, "error": "op.type required"})
                return
            rec = enqueue(op)
            self._json(200, {"ok": True, "id": rec["id"], "queued": True})
            return
        if path == "/ack":
            self._json(200, {"ok": True})
            return
        self._json(404, {"ok": False, "error": "not_found"})


def start(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict[str, Any]:
    global _server, _thread, _host, _port
    if is_running():
        return status()
    _host, _port = host, int(port)
    _server = ThreadingHTTPServer((host, int(port)), _Handler)
    _thread = threading.Thread(target=_server.serve_forever, name="roblox-bridge", daemon=True)
    _thread.start()
    return status()


def stop() -> dict[str, Any]:
    global _server, _thread
    if _server is not None:
        try:
            _server.shutdown()
        except Exception:
            pass
        try:
            _server.server_close()
        except Exception:
            pass
    _server = None
    _thread = None
    return status()
