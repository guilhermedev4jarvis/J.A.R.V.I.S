"""
core/secrets.py — load secrets from env / OS vault / encrypted store / api_keys.json.

Priority (highest first):
  1. Process environment variables
  2. Project-root `.env` (python-dotenv)
  3. Native OS vault (Windows DPAPI or keyring)
  4. Local encrypted vault file (config/secrets.vault) — machine-bound key
  5. config/api_keys.json (legacy plain text — auto-migrated then scrubbed)

Never commit real keys. `.env`, `config/api_keys.json`, `config/secrets.vault`
are git-ignored patterns.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, Optional

_dotenv_loaded = False
_migrated = False

# Secret field names that must not remain in plain api_keys.json
_SECRET_JSON_KEYS = (
    "gemini_api_key",
    "openai_api_key",
    "elevenlabs_api_key",
)


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
ENV_FILE = BASE_DIR / ".env"
CONFIG_FILE = BASE_DIR / "config" / "api_keys.json"
VAULT_FILE = BASE_DIR / "config" / "secrets.vault"
SERVICE = "mark-lvi-jarvis"

_ENV_MAP: dict[str, tuple[str, ...]] = {
    "gemini_api_key": (
        "MARK_GEMINI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ),
    "elevenlabs_api_key": (
        "MARK_ELEVENLABS_API_KEY",
        "ELEVENLABS_API_KEY",
    ),
    "openai_api_key": (
        "MARK_OPENAI_API_KEY",
        "OPENAI_API_KEY",
    ),
    "llm_url": (
        "MARK_LLM_URL",
        "OLLAMA_HOST",
        "OPENAI_BASE_URL",
    ),
    "llm_model": (
        "MARK_LLM_MODEL",
        "OLLAMA_MODEL",
    ),
    "llm_provider": (
        "MARK_LLM_PROVIDER",
    ),
}


def load_dotenv_once() -> None:
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    if ENV_FILE.is_file():
        load_dotenv(ENV_FILE, override=False)


def _env_get(*names: str) -> str:
    for name in names:
        val = os.environ.get(name)
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    return ""


# ── OS-native backends ────────────────────────────────────────────────────────

def _dpapi_protect(data: bytes) -> Optional[bytes]:
    if platform.system() != "Windows":
        return None
    try:
        import ctypes
        import ctypes.wintypes as wt

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        in_blob = DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
        out_blob = DATA_BLOB()
        if not crypt32.CryptProtectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            return None
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)
    except Exception:
        return None


def _dpapi_unprotect(data: bytes) -> Optional[bytes]:
    if platform.system() != "Windows":
        return None
    try:
        import ctypes
        import ctypes.wintypes as wt

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        in_blob = DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
        out_blob = DATA_BLOB()
        if not crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            return None
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)
    except Exception:
        return None


def _keyring_set(name: str, value: str) -> bool:
    try:
        import keyring
        keyring.set_password(SERVICE, name, value)
        return True
    except Exception:
        return False


def _keyring_get(name: str) -> str:
    try:
        import keyring
        val = keyring.get_password(SERVICE, name)
        return str(val).strip() if val else ""
    except Exception:
        return ""


def _machine_key() -> bytes:
    """Derive a local key for the vault file (not portable across machines)."""
    material = "|".join(
        [
            platform.node(),
            platform.system(),
            str(BASE_DIR.resolve()),
            os.environ.get("USERNAME") or os.environ.get("USER") or "mark",
        ]
    )
    return hashlib.sha256(("mark-lvi-vault-v1|" + material).encode("utf-8")).digest()


def _xor_cipher(data: bytes, key: bytes) -> bytes:
    out = bytearray(len(data))
    for i, b in enumerate(data):
        out[i] = b ^ key[i % len(key)]
    return bytes(out)


def _vault_read() -> dict[str, str]:
    if not VAULT_FILE.is_file():
        return {}
    try:
        raw = VAULT_FILE.read_bytes()
        if raw.startswith(b"DPAPI:"):
            plain = _dpapi_unprotect(base64.b64decode(raw[6:]))
            if not plain:
                return {}
            return json.loads(plain.decode("utf-8"))
        if raw.startswith(b"XOR1:"):
            blob = base64.b64decode(raw[5:])
            plain = _xor_cipher(blob, _machine_key())
            return json.loads(plain.decode("utf-8"))
        # legacy plain json vault
        return {k: str(v) for k, v in json.loads(raw.decode("utf-8")).items()}
    except Exception as e:
        print(f"[secrets] vault read failed: {e}")
        return {}


def _vault_write(data: dict[str, str]) -> None:
    VAULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    protected = _dpapi_protect(payload)
    if protected is not None:
        VAULT_FILE.write_bytes(b"DPAPI:" + base64.b64encode(protected))
        return
    # fallback machine-bound XOR (better than plain text; not HSM-grade)
    enc = _xor_cipher(payload, _machine_key())
    VAULT_FILE.write_bytes(b"XOR1:" + base64.b64encode(enc))


def store_secret(json_key: str, value: str) -> str:
    """Persist secret to keyring (preferred) and/or local vault. Returns backend id."""
    value = (value or "").strip()
    if not value:
        return "empty"
    if _keyring_set(json_key, value):
        # also mirror into vault for machines without keyring on next read path
        data = _vault_read()
        data[json_key] = value
        _vault_write(data)
        return "keyring+vault"
    data = _vault_read()
    data[json_key] = value
    _vault_write(data)
    return "vault"


def _vault_get(json_key: str) -> str:
    v = _keyring_get(json_key)
    if v:
        return v
    return str(_vault_read().get(json_key) or "").strip()


def read_json_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[secrets] Failed to load api_keys.json: {e}")
        return {}


def migrate_plain_secrets() -> dict[str, Any]:
    """Move secret fields from api_keys.json into the vault and scrub the file."""
    global _migrated
    if _migrated:
        return {"migrated": False, "reason": "already"}
    _migrated = True
    data = read_json_config()
    if not data:
        return {"migrated": False, "reason": "no_config"}
    moved = []
    for key in _SECRET_JSON_KEYS:
        val = str(data.get(key) or "").strip()
        if not val or val.lower() in ("your_key_here", "changeme", "xxx"):
            continue
        store_secret(key, val)
        data[key] = ""  # scrub plain text
        moved.append(key)
    if moved:
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            return {"migrated": False, "error": str(e), "moved": moved}
    return {"migrated": bool(moved), "moved": moved}


def apply_env_secrets(data: dict[str, Any] | None = None) -> dict[str, Any]:
    load_dotenv_once()
    migrate_plain_secrets()
    out = dict(data or read_json_config())
    for json_key, env_names in _ENV_MAP.items():
        val = _env_get(*env_names)
        if not val:
            val = _vault_get(json_key)
        if val:
            out[json_key] = val
    return out


def get_secret(json_key: str, default: str = "") -> str:
    load_dotenv_once()
    migrate_plain_secrets()
    env_names = _ENV_MAP.get(json_key)
    if env_names:
        val = _env_get(*env_names)
        if val:
            return val
    val = _vault_get(json_key)
    if val:
        return val
    data = read_json_config()
    return str(data.get(json_key) or default).strip()


def gemini_api_key() -> str:
    return get_secret("gemini_api_key")


def elevenlabs_api_key() -> str:
    return get_secret("elevenlabs_api_key")


def openai_api_key() -> str:
    return get_secret("openai_api_key")
