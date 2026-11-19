
"""Monitor de mudanca de paginas web com hash e diff."""
from __future__ import annotations

import hashlib
import json
import re
import time
from difflib import unified_diff
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.outcome import ask, done, failed

try:
    from core.action_hardening import atomic_write_json, project_root, safe_url
except Exception:
    def project_root() -> Path:
        return Path(__file__).resolve().parents[3]
    def atomic_write_json(path, data, **kw):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    def safe_url(url: str) -> str:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            raise ValueError("scheme")
        return url

try:
    import requests
except Exception:
    requests = None


def _store_path() -> Path:
    return project_root() / "memory" / "web_monitors.json"


def _load() -> dict:
    p = _store_path()
    if not p.is_file():
        return {"monitors": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {"monitors": {}}


def _save(data: dict) -> None:
    atomic_write_json(_store_path(), data)


def _is_private_host(host: str) -> bool:
    h = (host or "").lower()
    if h in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    if h.startswith("10.") or h.startswith("192.168.") or h.startswith("169.254."):
        return True
    if re.match(r"^172\.(1[6-9]|2\d|3[0-1])\.", h):
        return True
    return False


def _validate_url(url: str) -> str:
    u = safe_url(url)
    host = urlparse(u).hostname or ""
    if _is_private_host(host):
        raise ValueError("SSRF bloqueado: host privado/localhost")
    return u


def _normalize_html(html: str) -> str:
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    html = re.sub(r"(?is)<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html).strip()
    return html


def _fetch(url: str, css_selector: str = "") -> str:
    if requests is None:
        raise RuntimeError("requests nao instalado")
    r = requests.get(url, timeout=12, headers={"User-Agent": "JARVIS-PageMonitor/1.0"})
    r.raise_for_status()
    text = r.text
    if css_selector:
        try:
            from bs4 import BeautifulSoup  # type: ignore
            soup = BeautifulSoup(text, "html.parser")
            nodes = soup.select(css_selector)
            text = "\n".join(n.get_text(" ", strip=True) for n in nodes) if nodes else text
        except Exception:
            pass
    return _normalize_html(text)


def run(parameters=None, **_ctx) -> str:
    params = dict(parameters or {})
    action = str(params.get("action") or params.get("mode") or "listar").strip().lower()
    data = _load()
    monitors: dict = data.setdefault("monitors", {})

    if action in ("listar", "list"):
        return done("monitor_mudanca_pagina", monitors=list(monitors.keys()), count=len(monitors))

    if action in ("adicionar", "add", "watch"):
        url = str(params.get("url") or "").strip()
        alias = str(params.get("alias") or params.get("name") or "").strip()
        css = str(params.get("css_selector") or params.get("selector") or "").strip()
        if not url:
            return ask("monitor_mudanca_pagina", "Informe url=")
        try:
            url = _validate_url(url)
        except Exception as e:
            return failed("monitor_mudanca_pagina", str(e))
        alias = alias or urlparse(url).netloc or "page"
        try:
            body = _fetch(url, css)
        except Exception as e:
            return failed("monitor_mudanca_pagina", f"fetch falhou: {e}")
        h = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()
        monitors[alias] = {
            "url": url,
            "css_selector": css,
            "hash": h,
            "snapshot": body[:4000],
            "updated_at": time.time(),
        }
        _save(data)
        return done("monitor_mudanca_pagina", action="adicionar", alias=alias, hash=h)

    if action in ("remover", "remove", "delete"):
        alias = str(params.get("alias") or params.get("name") or "").strip()
        if not alias or alias not in monitors:
            return failed("monitor_mudanca_pagina", "alias nao encontrado")
        del monitors[alias]
        _save(data)
        return done("monitor_mudanca_pagina", action="remover", alias=alias)

    def _check_one(alias: str, item: dict) -> dict[str, Any]:
        try:
            body = _fetch(item["url"], item.get("css_selector") or "")
        except Exception as e:
            return {"alias": alias, "ok": False, "error": str(e)[:160]}
        h = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()
        changed = h != item.get("hash")
        diff_txt = ""
        if changed:
            old = (item.get("snapshot") or "").splitlines()
            new = body[:4000].splitlines()
            diff_txt = "\n".join(list(unified_diff(old, new, lineterm="", n=2))[:40])
            item["hash"] = h
            item["snapshot"] = body[:4000]
            item["updated_at"] = time.time()
        return {"alias": alias, "ok": True, "changed": changed, "hash": h, "diff": diff_txt[:1500]}

    if action in ("verificar", "check"):
        alias = str(params.get("alias") or params.get("name") or "").strip()
        if not alias or alias not in monitors:
            return failed("monitor_mudanca_pagina", "alias nao encontrado")
        res = _check_one(alias, monitors[alias])
        _save(data)
        return done("monitor_mudanca_pagina", action="verificar", **res)

    if action in ("verificar_todos", "check_all"):
        results = [_check_one(a, monitors[a]) for a in list(monitors.keys())]
        _save(data)
        return done("monitor_mudanca_pagina", action="verificar_todos", results=results, count=len(results))

    return failed("monitor_mudanca_pagina", f"action desconhecida: {action}")
