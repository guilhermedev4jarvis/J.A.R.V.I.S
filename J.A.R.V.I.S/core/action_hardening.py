"""Shared hardening helpers for actions: atomic IO, path/URL safety, safe subprocess."""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import tempfile
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

_FILE_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()

DEFAULT_NET_TIMEOUT = 12
DEFAULT_SUBPROCESS_TIMEOUT = 20

# Windows / system processes that must never be killed by actions
PROTECTED_PROCESS_NAMES = frozenset({
    "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe",
    "smss.exe", "svchost.exe", "explorer.exe", "system", "registry",
    "python.exe", "pythonw.exe", "python",  # protect assistant runtime by default
})

ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def project_root() -> Path:
    here = Path(__file__).resolve().parent
    for p in [here, *here.parents]:
        if (p / "config").is_dir() and ((p / "core").is_dir() or (p / "main").exists()):
            return p
    return here.parent


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve()) if path.exists() else str(path)
    with _LOCKS_GUARD:
        if key not in _FILE_LOCKS:
            _FILE_LOCKS[key] = threading.Lock()
        return _FILE_LOCKS[key]


def atomic_write_text(path: Path | str, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_for(path)
    with lock:
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding=encoding, errors="replace") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise


def atomic_write_json(path: Path | str, data: Any, **json_kw: Any) -> None:
    json_kw.setdefault("ensure_ascii", False)
    json_kw.setdefault("indent", 2)
    atomic_write_text(path, json.dumps(data, **json_kw) + "\n")


def safe_resolve_path(
    user_path: str | Path,
    *,
    allowed_roots: Optional[Iterable[Path]] = None,
    must_exist: bool = False,
) -> Path:
    """Resolve path and ensure it stays under allowed roots (default: home + project)."""
    raw = Path(str(user_path)).expanduser()
    resolved = raw.resolve()
    roots = list(allowed_roots) if allowed_roots is not None else [Path.home(), project_root()]
    roots_res = [r.expanduser().resolve() for r in roots]
    if not any(resolved == r or r in resolved.parents or resolved in r.parents or str(resolved).startswith(str(r)) for r in roots_res):
        # allow if under any root
        ok = False
        for r in roots_res:
            try:
                resolved.relative_to(r)
                ok = True
                break
            except ValueError:
                continue
        if not ok:
            raise PermissionError(f"path fora das pastas permitidas: {resolved}")
    if must_exist and not resolved.exists():
        raise FileNotFoundError(str(resolved))
    return resolved


def safe_url(url: str) -> str:
    u = (url or "").strip()
    parsed = urlparse(u)
    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
        raise ValueError(f"URL scheme nao permitido: {parsed.scheme!r}")
    if not parsed.netloc:
        raise ValueError("URL sem host")
    # block obvious local SSRF targets optionally — allow localhost for home automation
    return u


def is_protected_process(name: str) -> bool:
    n = (name or "").strip().lower()
    if not n:
        return True
    if not n.endswith(".exe") and "." not in n:
        n_exe = n + ".exe"
    else:
        n_exe = n
    return n in PROTECTED_PROCESS_NAMES or n_exe in PROTECTED_PROCESS_NAMES


def run_subprocess(
    args: list[str],
    *,
    timeout: float = DEFAULT_SUBPROCESS_TIMEOUT,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
) -> tuple[int, str, str]:
    """Safe subprocess: no shell, explicit timeout, resilient decoding."""
    if not args or not isinstance(args, (list, tuple)):
        raise ValueError("args deve ser lista sem shell=True")
    kw: dict[str, Any] = {
        "args": list(args),
        "capture_output": True,
        "timeout": timeout,
        "cwd": cwd,
        "env": env,
    }
    if os.name == "nt":
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    try:
        proc = subprocess.run(**kw)
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except FileNotFoundError as e:
        return 127, "", str(e)

    def _dec(b: Any) -> str:
        if b is None:
            return ""
        if isinstance(b, str):
            return b
        for enc in ("utf-8", "cp850", "cp1252"):
            try:
                return b.decode(enc)
            except Exception:
                continue
        return b.decode("utf-8", errors="replace")

    return proc.returncode, _dec(proc.stdout).strip(), _dec(proc.stderr).strip()


def sanitize_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r"[\\\\/:*?\"<>|]+", "_", (name or "").strip())
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name or "file")[:max_len]


__all__ = [
    "atomic_write_text",
    "atomic_write_json",
    "safe_resolve_path",
    "safe_url",
    "is_protected_process",
    "run_subprocess",
    "sanitize_filename",
    "project_root",
    "PROTECTED_PROCESS_NAMES",
    "DEFAULT_NET_TIMEOUT",
    "DEFAULT_SUBPROCESS_TIMEOUT",
]
