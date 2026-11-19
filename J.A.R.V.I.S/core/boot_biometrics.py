from __future__ import annotations
import os
from typing import Any, Callable, Optional
from core.preboot_gate import DEFAULT_PLAIN as DEFAULT_PASSWORD, DEFAULT_HASH, expected_hash, password_ok

LogFn = Callable[[str], None]

def master_password() -> str:
    return (os.getenv("JARVIS_BOOT_PASSWORD") or DEFAULT_PASSWORD).strip()

def hard_exit(reason: str = "denied", ui: Any = None) -> None:
    print(f"[BOOT] hard_exit: {reason}")
    os._exit(1)

def enforce_startup_biometrics(ui: Any = None, log: Optional[LogFn] = None) -> bool:
    if (os.getenv("JARVIS_SKIP_FACE_BOOT") or "").strip().lower() in ("1", "true", "yes", "on"):
        msg = "Boot liberado (JARVIS_SKIP_FACE_BOOT)."
        print("[BOOT]", msg)
        if log:
            try: log(msg)
            except Exception: pass
        return True
    # sem UI/camera no Codespace: libera se perfil existir ou skip
    try:
        from core import face_auth
        if face_auth.has_profile() or (os.getenv("JARVIS_SKIP_CAMERA") or "").strip().lower() in ("1", "true", "yes"):
            print("[BOOT] face gate soft-pass")
            return True
    except Exception as e:
        print("[BOOT] face unavailable:", e)
    print("[BOOT] face required but unavailable — set JARVIS_SKIP_FACE_BOOT=1")
    return False
