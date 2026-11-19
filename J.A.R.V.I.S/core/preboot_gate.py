from __future__ import annotations
import hashlib, os, threading
from pathlib import Path

DEFAULT_PLAIN = "123gui834"
DEFAULT_HASH = "79d8d70cc2b3d9cf76d36ea9d91557e5c60058e1e9dd9d3a819aa86b15e7930d"
MAX_ATTEMPTS = 3
_validated = False
_lock = threading.Lock()

def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

def expected_hash() -> str:
    h = (os.getenv("JARVIS_BOOT_PASSWORD_HASH") or "").strip().lower()
    if len(h) == 64:
        return h
    p = (os.getenv("JARVIS_BOOT_PASSWORD") or "").strip()
    return _sha256(p) if p else DEFAULT_HASH

def password_ok(candidate: str | None) -> bool:
    return bool(candidate) and _sha256(str(candidate).strip()) == expected_hash()

def is_validated() -> bool:
    return _validated

def run_preboot_gate(*, force: bool = False) -> bool:
    global _validated
    with _lock:
        if _validated and not force:
            return True
        if (os.getenv("JARVIS_SKIP_PREBOOT") or "").strip().lower() in ("1", "true", "yes", "on"):
            _validated = True
            print("[PREBOOT] skipped")
            return True
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                cand = input(f"[PREBOOT] senha ({attempt}/{MAX_ATTEMPTS}): ").strip()
            except Exception:
                cand = ""
            if password_ok(cand):
                _validated = True
                print("[PREBOOT] ok")
                return True
            print("[PREBOOT] invalida")
        os._exit(1)
        return False
