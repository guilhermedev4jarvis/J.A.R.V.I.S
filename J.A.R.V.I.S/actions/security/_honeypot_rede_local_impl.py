
"""TCP honeypot local multi-client — defensive monitoring (hardened)."""
from __future__ import annotations

import json
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.outcome import ask, done, failed

try:
    from core.action_hardening import project_root
except Exception:
    def project_root() -> Path:
        return Path(__file__).resolve().parents[3]

_STATE_LOCK = threading.Lock()
_SEM = threading.Semaphore(10)
_SERVER: socket.socket | None = None
_THREAD: threading.Thread | None = None
_RUNNING = False
_PORT = 0
_BANNER = b"220 JARVIS-HONEYPOT ready\r\n"
_HISTORY: list[dict[str, Any]] = []
_MAX_HISTORY = 200
_IP_COOLDOWN: dict[str, float] = {}
_COOLDOWN_SEC = 60.0


def _local_ips() -> set[str]:
    ips = {"127.0.0.1", "::1", "0.0.0.0"}
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ips.add(info[4][0])
    except Exception:
        pass
    return ips


def _history_jsonl() -> Path:
    return project_root() / "memory" / "audit" / "intruder_events.jsonl"


def _append_history(event: dict[str, Any]) -> None:
    global _HISTORY
    event = dict(event)
    event.setdefault("ts", datetime.now(timezone.utc).isoformat())
    event.setdefault("source", "honeypot_rede_local")
    with _STATE_LOCK:
        _HISTORY.append(event)
        _HISTORY = _HISTORY[-_MAX_HISTORY:]
    path = _history_jsonl()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass
    try:
        from core.event_bus import EventBus
        EventBus.get().publish("security.honeypot", event)
    except Exception:
        pass


def _client_handler(conn: socket.socket, addr: tuple) -> None:
    peer_ip = addr[0]
    peer = f"{addr[0]}:{addr[1]}"
    if peer_ip in _local_ips():
        try:
            conn.close()
        except OSError:
            pass
        return
    now = time.time()
    with _STATE_LOCK:
        last = _IP_COOLDOWN.get(peer_ip, 0)
        if now - last < _COOLDOWN_SEC:
            try:
                conn.close()
            except OSError:
                pass
            return
        _IP_COOLDOWN[peer_ip] = now

    if not _SEM.acquire(blocking=False):
        try:
            conn.close()
        except OSError:
            pass
        return
    try:
        _append_history({"event": "connect", "peer": peer})
        conn.settimeout(2.0)
        try:
            conn.sendall(_BANNER)
        except OSError:
            return
        try:
            data = conn.recv(512)
        except socket.timeout:
            data = b""
        except OSError:
            data = b""
        if data:
            _append_history({
                "event": "payload",
                "peer": peer,
                "bytes": len(data),
                "preview": data.decode("utf-8", errors="replace")[:200],
            })
        try:
            conn.sendall(b"502 Command not implemented\r\n")
        except OSError:
            pass
    finally:
        try:
            conn.close()
        except OSError:
            pass
        _append_history({"event": "disconnect", "peer": peer})
        _SEM.release()


def _serve(port: int) -> None:
    global _RUNNING, _SERVER
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", port))
        srv.listen(32)
        srv.settimeout(1.0)
        _SERVER = srv
        _RUNNING = True
        while _RUNNING:
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=_client_handler, args=(conn, addr), daemon=True).start()
    finally:
        _RUNNING = False
        try:
            srv.close()
        except OSError:
            pass
        _SERVER = None


def run(parameters=None, **_ctx) -> str:
    global _THREAD, _RUNNING, _PORT, _BANNER
    params = dict(parameters or {})
    action = str(params.get("action") or params.get("mode") or "status").strip().lower()

    if action in ("status", "estado"):
        with _STATE_LOCK:
            hist_n = len(_HISTORY)
        return done("honeypot_rede_local", action="status", running=_RUNNING, port=_PORT if _RUNNING else None, history_count=hist_n)

    if action in ("historico", "history", "log"):
        with _STATE_LOCK:
            items = list(_HISTORY)[-50:]
        return done("honeypot_rede_local", action="historico", events=items, count=len(items))

    if action in ("parar", "stop", "off"):
        _RUNNING = False
        if _SERVER is not None:
            try:
                _SERVER.close()
            except OSError:
                pass
        if _THREAD and _THREAD.is_alive():
            _THREAD.join(timeout=3.0)
        _THREAD = None
        return done("honeypot_rede_local", action="parar", running=False)

    if action in ("iniciar", "start", "on"):
        if _RUNNING:
            return done("honeypot_rede_local", action="iniciar", running=True, port=_PORT, message="ja em execucao")
        try:
            port = int(params.get("port") or 2222)
        except (TypeError, ValueError):
            return failed("honeypot_rede_local", "porta invalida")
        if port < 1024 or port > 65535:
            return failed("honeypot_rede_local", "porta deve estar entre 1024 e 65535")
        banner = str(params.get("banner") or "220 JARVIS-HONEYPOT ready").encode("utf-8", errors="replace") + b"\r\n"
        _BANNER = banner
        _PORT = port
        _THREAD = threading.Thread(target=_serve, args=(port,), daemon=True, name="jarvis-honeypot")
        _THREAD.start()
        time.sleep(0.2)
        _append_history({"event": "start", "port": port})
        return done("honeypot_rede_local", action="iniciar", running=True, port=port)

    return ask("honeypot_rede_local", "action=iniciar|parar|status|historico")
