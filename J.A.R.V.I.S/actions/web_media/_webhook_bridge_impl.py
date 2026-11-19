"""webhook_bridge — named outbound webhooks for IoT / mobile alerts."""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import threading
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from core.outcome import ask, done, failed

_BASE = Path(__file__).resolve().parents[2]
_CFG = _BASE / "config" / "webhooks.json"
_lock = threading.Lock()

# Hosts/CIDRs blocked by default (SSRF protection)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _load() -> dict:
    if not _CFG.is_file():
        return {"version": 1, "endpoints": {}}
    try:
        return json.loads(_CFG.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "endpoints": {}}


def _save(data: dict) -> None:
    _CFG.parent.mkdir(parents=True, exist_ok=True)
    _CFG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _resolve_secret_placeholders(text: str) -> str:
    """Replace {{secret:name}} using core.secrets.get_secret."""
    if not text or "{{secret:" not in text:
        return text

    def repl(m):
        key = m.group(1).strip()
        try:
            from core.secrets import get_secret
            return get_secret(key, "")
        except Exception:
            return ""

    return re.sub(r"\{\{\s*secret:([A-Za-z0-9_\-]+)\s*\}\}", repl, text)


def _validate_url(url: str, allow_private: bool = False) -> tuple[bool, str]:
    try:
        u = urlparse(url)
    except Exception as e:
        return False, f"invalid url: {e}"
    if u.scheme not in ("http", "https"):
        return False, "only http/https allowed"
    host = u.hostname or ""
    if not host:
        return False, "missing host"
    # block obvious metadata endpoints by name
    if host.lower() in {"metadata.google.internal", "metadata"}:
        return False, "metadata host blocked"
    try:
        infos = socket.getaddrinfo(host, u.port or 80, type=socket.SOCK_STREAM)
    except Exception as e:
        return False, f"dns failed: {e}"
    if allow_private:
        return True, "ok"
    for info in infos:
        ip_s = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_s)
        except Exception:
            continue
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                return False, f"private/reserved address blocked: {ip}"
    return True, "ok"


def _owner_ok(name: str) -> tuple[bool, str]:
    try:
        from core import owner_gate
        if hasattr(owner_gate, "require_unlocked_for_critical"):
            r = owner_gate.require_unlocked_for_critical("webhook_bridge", name, camera=True)
            if isinstance(r, dict):
                return bool(r.get("accepted")), str(r.get("detail") or "")
        return True, "ok"
    except Exception as e:
        return False, f"owner_gate error: {e}"


def _http_request(method: str, url: str, headers: dict, body: str, timeout: float = 15.0) -> tuple[int, str]:
    import urllib.request
    data = body.encode("utf-8") if body is not None and method.upper() != "GET" else None
    req = urllib.request.Request(url, data=data, method=method.upper())
    for k, v in (headers or {}).items():
        req.add_header(str(k), str(v))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), (resp.read()[:500]).decode("utf-8", "replace")
    except Exception as e:
        # urllib raises HTTPError with code
        code = getattr(e, "code", None)
        if code is not None:
            return int(code), str(e)[:300]
        return 0, str(e)[:300]


def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or p.get("mode") or "list").strip().lower()
    data = _load()
    endpoints = data.setdefault("endpoints", {})

    if action in ("list", "show"):
        names = sorted(endpoints.keys())
        return done(
            "webhook_bridge",
            op="list",
            count=len(names),
            endpoints=",".join(names) or "(none)",
        )

    if action in ("register", "add", "create"):
        name = str(p.get("name") or "").strip()
        url = str(p.get("url") or "").strip()
        if not name:
            return ask("webhook_bridge", "Qual o nome do endpoint?")
        if not url:
            return ask("webhook_bridge", "Qual a URL do webhook?")
        allow_private = str(p.get("allow_private_hosts") or "").lower() in ("1", "true", "yes")
        ok, why = _validate_url(url, allow_private=allow_private)
        if not ok:
            return failed("webhook_bridge", why, name=name)
        entry = {
            "url": url,
            "method": str(p.get("method") or "POST").upper(),
            "headers": p.get("headers") if isinstance(p.get("headers"), dict) else {"Content-Type": "application/json"},
            "body_template": str(p.get("body_template") or "{{message}}"),
            "requires_owner_gate": str(p.get("requires_owner_gate") or "true").lower() not in ("0", "false", "no"),
            "allow_private_hosts": allow_private,
            "description": str(p.get("description") or ""),
        }
        if isinstance(p.get("headers"), str):
            try:
                entry["headers"] = json.loads(p["headers"])
            except Exception:
                pass
        with _lock:
            endpoints[name] = entry
            _save(data)
        return done("webhook_bridge", op="register", name=name, method=entry["method"])

    if action in ("trigger", "send", "fire", "call"):
        name = str(p.get("name") or p.get("endpoint") or "").strip()
        if not name:
            return ask("webhook_bridge", "Qual endpoint disparar? (ex: alerta_celular)")
        entry = endpoints.get(name)
        if not entry:
            return failed("webhook_bridge", f"endpoint não registrado: {name}")

        if entry.get("requires_owner_gate", True):
            ok, detail = _owner_ok(name)
            if not ok:
                return failed("webhook_bridge", f"owner_gate denied: {detail}", name=name)

        url = _resolve_secret_placeholders(str(entry.get("url") or ""))
        allow_private = bool(entry.get("allow_private_hosts"))
        ok, why = _validate_url(url, allow_private=allow_private)
        if not ok:
            return failed("webhook_bridge", why, name=name)

        message = str(p.get("message") or p.get("text") or p.get("body") or "JARVIS alert").strip()
        body_t = str(entry.get("body_template") or "{{message}}")
        body = body_t.replace("{{message}}", message)
        body = _resolve_secret_placeholders(body)

        headers = {}
        for k, v in (entry.get("headers") or {}).items():
            headers[str(k)] = _resolve_secret_placeholders(str(v))

        method = str(entry.get("method") or "POST").upper()

        # Allow dependency injection for tests
        http_fn = p.get("_http_fn") or _http_request
        status, resp = http_fn(method, url, headers, body)
        if status and 200 <= int(status) < 300:
            return done("webhook_bridge", op="trigger", name=name, http_status=status)
        return failed(
            "webhook_bridge",
            f"http status {status}: {resp[:120]}",
            name=name,
            http_status=status,
        )

    if action in ("remove", "delete"):
        name = str(p.get("name") or "").strip()
        if not name or name not in endpoints:
            return failed("webhook_bridge", f"endpoint não encontrado: {name or '(vazio)'}")
        with _lock:
            del endpoints[name]
            _save(data)
        return done("webhook_bridge", op="remove", name=name)

    return failed("webhook_bridge", f"action desconhecida: {action}")
