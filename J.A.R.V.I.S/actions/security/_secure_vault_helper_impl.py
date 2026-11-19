"""Retrieve secrets via core.secrets / owner_gate; clipboard auto-clear."""
from __future__ import annotations

import threading
import time
from typing import Optional

from core.outcome import ask, done, failed


def _owner_ok(player=None) -> tuple[bool, str]:
    try:
        from core import owner_gate
        if hasattr(owner_gate, "is_session_locked") and owner_gate.is_session_locked():
            if hasattr(owner_gate, "require_unlocked_for_critical"):
                gate = owner_gate.require_unlocked_for_critical(
                    "secure_vault_helper", "get", camera=True
                )
                if gate is False or (isinstance(gate, dict) and not gate.get("ok", True)):
                    return False, "owner_gate denied — unlock required"
        if hasattr(owner_gate, "verify_owner_quick"):
            ok = owner_gate.verify_owner_quick()
            if ok is False:
                return False, "owner verification failed"
    except Exception as e:
        return False, f"owner_gate error: {e}"
    return True, "ok"


def _get_secret(key: str) -> Optional[str]:
    try:
        from core import secrets as sec
        for fn in ("get", "get_secret", "retrieve", "load"):
            if hasattr(sec, fn):
                val = getattr(sec, fn)(key)
                if val:
                    return str(val)
        if hasattr(sec, "vault") and isinstance(sec.vault, dict) and key in sec.vault:
            return str(sec.vault[key])
    except Exception:
        pass
    try:
        import json
        from pathlib import Path
        path = Path(__file__).resolve().parents[2] / "config" / "secrets.vault"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if key in data:
                    return str(data[key])
                nested = data.get("secrets")
                if isinstance(nested, dict) and key in nested:
                    return str(nested[key])
    except Exception:
        pass
    return None


def _clipboard_set(text: str) -> bool:
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        try:
            import actions.desktop.clipboard_smart as clipboard_smart
            clipboard_smart.clipboard_smart({"action": "set", "text": text})
            return True
        except Exception:
            return False


def _clipboard_clear() -> None:
    try:
        import pyperclip
        pyperclip.copy("")
    except Exception:
        pass


def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or p.get("mode") or "get").strip().lower()
    key = str(p.get("key") or p.get("name") or p.get("secret") or "").strip()
    ttl = int(float(p.get("ttl") or p.get("seconds") or 15))
    ttl = max(5, min(ttl, 60))

    if action in ("list_keys", "list"):
        ok, why = _owner_ok(player)
        if not ok:
            return failed("secure_vault_helper", why)
        keys = []
        try:
            from core import secrets as sec
            if hasattr(sec, "list_keys"):
                keys = list(sec.list_keys())
        except Exception:
            pass
        if not keys:
            try:
                import json
                from pathlib import Path
                path = Path(__file__).resolve().parents[2] / "config" / "secrets.vault"
                if path.is_file():
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        blob = data.get("secrets") if isinstance(data.get("secrets"), dict) else data
                        if isinstance(blob, dict):
                            keys = list(blob.keys())
            except Exception:
                keys = []
        return done("secure_vault_helper", op="list", keys=",".join(keys[:50]) or "(none)")

    if action in ("get", "copy", "clipboard"):
        if not key:
            return ask("secure_vault_helper", "Qual chave do cofre recuperar?")
        ok, why = _owner_ok(player)
        if not ok:
            return failed("secure_vault_helper", why, key=key)
        val = _get_secret(key)
        if not val:
            return failed("secure_vault_helper", "secret not found", key=key)
        if not _clipboard_set(val):
            return failed("secure_vault_helper", "could not copy to clipboard", key=key)

        def _clear():
            time.sleep(ttl)
            _clipboard_clear()
            print(f"[vault] clipboard cleared after {ttl}s for key={key}")

        threading.Thread(target=_clear, daemon=True, name="vault-clip-clear").start()
        return done(
            "secure_vault_helper",
            op="copy",
            key=key,
            ttl=ttl,
            note="value copied; auto-clear scheduled",
        )

    return failed("secure_vault_helper", f"unknown action {action}")
