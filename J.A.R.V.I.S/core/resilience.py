"""core/resilience.py — timeouts, retries, atomic JSON, offline-friendly HTTP."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from core.retry import retry_call

DEFAULT_CONNECT = 4.0
DEFAULT_READ = 10.0
_IO_LOCKS: dict[str, threading.Lock] = {}
_IO_META = threading.Lock()


def file_lock(path: str | Path) -> threading.Lock:
    key = str(Path(path).resolve())
    with _IO_META:
        if key not in _IO_LOCKS:
            _IO_LOCKS[key] = threading.Lock()
        return _IO_LOCKS[key]


def atomic_write_text(path: str | Path, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = file_lock(path)
    with lock:
        fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding=encoding) as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def atomic_write_json(path: str | Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def safe_read_json(path: str | Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.is_file():
        return {} if default is None else default
    lock = file_lock(path)
    with lock:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {} if default is None else default


def http_request(
    method: str,
    url: str,
    *,
    timeout: tuple[float, float] | float = (DEFAULT_CONNECT, DEFAULT_READ),
    attempts: int = 3,
    offline_result: Any = None,
    **kwargs: Any,
) -> Any:
    """requests wrapper with timeout + exponential backoff. Returns offline_result on total failure if set."""
    import requests

    method = method.upper()
    kwargs.setdefault("timeout", timeout)

    def _once():
        resp = requests.request(method, url, **kwargs)
        if resp.status_code >= 500:
            raise requests.HTTPError(f"server {resp.status_code}", response=resp)
        return resp

    try:
        return retry_call(
            _once,
            attempts=attempts,
            base_delay=0.4,
            max_delay=3.0,
            retry_on=lambda e: isinstance(
                e,
                (
                    requests.Timeout,
                    requests.ConnectionError,
                    requests.HTTPError,
                    OSError,
                ),
            ),
        )
    except Exception as e:
        if offline_result is not None:
            return offline_result if not callable(offline_result) else offline_result(e)
        raise


def sanitize_phone(raw: str) -> str:
    return "".join(ch for ch in str(raw or "") if ch.isdigit())


def sanitize_plate(raw: str) -> str:
    return "".join(ch for ch in str(raw or "").upper() if ch.isalnum())[:10]


def safe_path(raw: str, base: Path) -> Optional[Path]:
    if not raw:
        return None
    try:
        p = Path(raw).expanduser().resolve()
        base_r = base.resolve()
        if base_r in p.parents or p == base_r or str(p).startswith(str(base_r)):
            return p
    except Exception:
        return None
    return None
