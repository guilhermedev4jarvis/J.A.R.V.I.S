"""
core/owner_gate.py — first-run owner enrollment + biometric gate for critical acts.

First run (when profiles are missing)
-------------------------------------
Required files under memory/biometrics/:

    vozdono.mp3          short recording of the owner's wake/command phrase
    fotobase1.jpg        face, front
    fotobase2.jpg        face, one side
    fotobase3.jpg        face, other side
    owner_command.json   {"phrase": "ok jarvis", "created_at": "..."}

If any are missing, needs_enrollment() is True and the UI / main should run
the enrollment wizard before accepting autonomous actuation.

Critical actions (shutdown, restart, factory-style resets, mass delete, …)
require a fresh voice OR face match (user chooses). The model cannot skip this.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path
import os
import threading
import time
from typing import Any, Optional

_BASE = Path(__file__).resolve().parents[1]
_BIO = _BASE / "memory" / "biometrics"

VOICE_FILE = _BIO / "vozdono.mp3"
VOICE_WAV = _BIO / "vozdono.wav"  # working copy for fingerprinting
FACE_FILES = (
    _BIO / "fotobase1.jpg",  # frente
    _BIO / "fotobase2.jpg",  # lado A
    _BIO / "fotobase3.jpg",  # lado B
)
COMMAND_FILE = _BIO / "owner_command.json"
STATE_FILE = _BIO / "owner_gate_state.json"

# Actions that always need owner biometrics in addition to the HUD confirm.
CRITICAL_ACTIONS = frozenset({
    "shutdown", "restart", "power_off", "reboot",
    "factory_reset", "reset", "wipe", "format",
    "delete_all", "mass_delete",
})

CRITICAL_TOOL_NAMES = frozenset({
    # legacy names
    "shutdown_jarvis",
    "powershell_cmd",
    "file_controller",
    "send_message",
    "whatsapp_web",
    "self_program",
    "computer_control",
    "computer_settings",
    "desktop_agent",
    # Stage 1 consolidated names (must stay gated)
    "powershell_tool",
    "file_manager",
    "code_studio",
    "desktop_control",
    "network_manager",
    "system_monitor",  # governor can be sensitive; gate only when action critical below
})


def _ensure_bio() -> None:
    _BIO.mkdir(parents=True, exist_ok=True)


def enrollment_status() -> dict[str, Any]:
    """What is present / missing for first-run readiness."""
    _ensure_bio()
    voice_ok = VOICE_FILE.is_file() or VOICE_WAV.is_file()
    faces = {p.name: p.is_file() for p in FACE_FILES}
    faces_ok = all(faces.values())
    cmd = load_command_phrase()
    return {
        "voice": voice_ok,
        "voice_path": str(VOICE_FILE if VOICE_FILE.is_file() else VOICE_WAV),
        "faces": faces,
        "faces_ok": faces_ok,
        "phrase": cmd.get("phrase") if cmd else None,
        "complete": bool(voice_ok and faces_ok and cmd and cmd.get("phrase")),
        "bio_dir": str(_BIO),
    }


def needs_enrollment() -> bool:
    return not enrollment_status()["complete"]


def load_command_phrase() -> Optional[dict]:
    if not COMMAND_FILE.is_file():
        return None
    try:
        data = json.loads(COMMAND_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("phrase"):
            return data
    except Exception:
        pass
    return None


def save_command_phrase(phrase: str) -> dict:
    _ensure_bio()
    phrase = " ".join((phrase or "").strip().lower().split())
    if not phrase:
        raise ValueError("phrase empty")
    data = {
        "phrase": phrase,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    COMMAND_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def _ffmpeg_to_wav(src: Path, dst: Path) -> bool:
    """Convert mp3/ogg/… → wav 16 kHz mono via ffmpeg if available."""
    try:
        r = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(src),
                "-ac", "1", "-ar", "16000", "-sample_fmt", "s16",
                str(dst),
            ],
            capture_output=True,
            timeout=60,
        )
        return r.returncode == 0 and dst.is_file()
    except Exception:
        return False


def ensure_voice_wav() -> Path:
    """Return a WAV path usable by voice_auth (creates from mp3 if needed)."""
    _ensure_bio()
    if VOICE_WAV.is_file():
        return VOICE_WAV
    if VOICE_FILE.is_file():
        if _ffmpeg_to_wav(VOICE_FILE, VOICE_WAV):
            return VOICE_WAV
        # Last resort: try pydub
        try:
            from pydub import AudioSegment
            seg = AudioSegment.from_file(str(VOICE_FILE))
            seg = seg.set_channels(1).set_frame_rate(16000)
            seg.export(str(VOICE_WAV), format="wav")
            return VOICE_WAV
        except Exception as e:
            raise RuntimeError(
                f"cannot decode {VOICE_FILE.name} to wav (install ffmpeg): {e}"
            ) from e
    raise FileNotFoundError("vozdono.mp3 / vozdono.wav missing — run enrollment")


def register_voice_file(src: str | Path, *, phrase: Optional[str] = None) -> dict[str, Any]:
    """Copy owner voice sample into vozdono.mp3 (or .wav) and enroll fingerprint."""
    from core import voice_auth

    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError(str(src))
    _ensure_bio()

    suffix = src.suffix.lower()
    if suffix == ".mp3":
        shutil.copy2(src, VOICE_FILE)
        # build wav for fingerprint
        if not _ffmpeg_to_wav(VOICE_FILE, VOICE_WAV):
            # keep wav copy of raw if already wav-like failure
            pass
    elif suffix == ".wav":
        shutil.copy2(src, VOICE_WAV)
        # also try to produce mp3 for the canonical name the user expects
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(VOICE_WAV), "-codec:a", "libmp3lame", "-qscale:a", "4", str(VOICE_FILE)],
                capture_output=True, timeout=60,
            )
        except Exception:
            pass
    else:
        # convert anything else → wav + mp3
        if not _ffmpeg_to_wav(src, VOICE_WAV):
            raise RuntimeError(f"unsupported audio format: {suffix}")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(VOICE_WAV), "-codec:a", "libmp3lame", "-qscale:a", "4", str(VOICE_FILE)],
                capture_output=True, timeout=60,
            )
        except Exception:
            pass

    wav = ensure_voice_wav()
    info = voice_auth.enroll_from_wav(wav, label="owner")
    out = {"voice": info, "files": {"mp3": VOICE_FILE.is_file(), "wav": VOICE_WAV.is_file()}}
    if phrase:
        out["command"] = save_command_phrase(phrase)
    return out


def register_face_slot(slot: int, src: str | Path) -> dict[str, Any]:
    """slot 1..3 → fotobase{slot}.jpg and rebuild combined face profile from all present."""
    if slot not in (1, 2, 3):
        raise ValueError("slot must be 1, 2 or 3")
    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError(str(src))
    _ensure_bio()
    dest = FACE_FILES[slot - 1]
    # Normalize to JPEG via PIL when possible
    try:
        from PIL import Image
        img = Image.open(src).convert("RGB")
        img.save(dest, format="JPEG", quality=92)
    except Exception:
        shutil.copy2(src, dest)

    return {"slot": slot, "path": str(dest), "enrolled_face": _rebuild_face_profile()}


def _rebuild_face_profile() -> dict[str, Any]:
    """Average embeddings of all three base photos into one owner face profile."""
    from core import face_auth
    import numpy as np

    present = [p for p in FACE_FILES if p.is_file()]
    if not present:
        return {"ok": False, "reason": "no face photos"}

    vectors = []
    method = None
    for p in present:
        try:
            # Prefer strict face detect; fall back to full-frame for awkward angles
            try:
                vec, method = face_auth._embed_image(face_auth._read_image(p))
            except RuntimeError:
                img = face_auth._read_image(p)
                h, w = img.shape[:2]
                vec = face_auth._embed_hist(img, (0, 0, w, h))
                method = "opencv_hist_fullframe"
            vectors.append(vec)
        except Exception as e:
            print(f"[owner_gate] face embed skip {p.name}: {e}")

    if not vectors:
        return {"ok": False, "reason": "no embeddable faces"}

    avg = np.mean(np.stack(vectors, axis=0), axis=0)
    avg = avg / (np.linalg.norm(avg) + 1e-9)
    profile = {
        "label": "owner",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": method or "avg",
        "dim": int(avg.size),
        "vector": avg.tolist(),
        "threshold": 0.80,
        "sources": [p.name for p in present],
    }
    face_auth._ensure_dir()
    face_auth._PROFILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return {"ok": True, "photos": len(present), "dim": profile["dim"], "method": profile["method"]}


def verify_voice(probe_path: str | Path, *, threshold: Optional[float] = None) -> dict[str, Any]:
    from core import voice_auth
    ensure_voice_wav()
    # Ensure enrolled fingerprint exists from vozdono
    if not voice_auth.has_profile():
        voice_auth.enroll_from_wav(ensure_voice_wav(), label="owner")
    score = voice_auth.verify_wav(probe_path, threshold=threshold)
    return {
        "accepted": score.accepted,
        "score": round(score.score, 4),
        "threshold": score.threshold,
        "detail": score.detail,
        "method": "voice",
    }


def verify_face(image_path: Optional[str | Path] = None, *, camera: bool = False,
                threshold: Optional[float] = None) -> dict[str, Any]:
    from core import face_auth
    if not face_auth.has_profile():
        if any(p.is_file() for p in FACE_FILES):
            _rebuild_face_profile()
        if not face_auth.has_profile():
            return {"accepted": False, "score": 0.0, "detail": "no_face_profile", "method": "face"}
    if camera:
        score = face_auth.verify_from_camera(threshold=threshold)
    else:
        if not image_path:
            return {"accepted": False, "score": 0.0, "detail": "no_image", "method": "face"}
        score = face_auth.verify_image(image_path, threshold=threshold)
    return {
        "accepted": score.accepted,
        "score": round(score.score, 4),
        "threshold": score.threshold,
        "detail": score.detail,
        "method": "face",
    }



def master_password() -> str:
    import os
    return (
        os.getenv("JARVIS_BOOT_PASSWORD")
        or os.getenv("JARVIS_MASTER_PASSWORD")
        or "123gui834"
    ).strip()


def password_ok(candidate: str | None) -> bool:
    return bool(candidate) and str(candidate).strip() == master_password()


def extract_password_from_text(text: str | None) -> str | None:
    """Parse 'senha 123...' or '/senha 123...' from free text."""
    import re
    if not text:
        return None
    m = re.search(r"(?:/senha|senha)\s+(\S+)", str(text), flags=re.I)
    return m.group(1) if m else None


def is_critical(tool_name: str = "", action: str = "") -> bool:
    a = (action or "").strip().lower()
    t = (tool_name or "").strip().lower()
    if a in CRITICAL_ACTIONS:
        return True
    if t in CRITICAL_TOOL_NAMES:
        # system_monitor is broad — only governor/hardware write-ish modes are critical
        if t == "system_monitor" and a not in (
            "governor", "resource_governor", "resource", "hardware_sensors", "hw", "sensors"
        ):
            return False
        return True
    if any(k in a for k in ("shutdown", "restart", "wipe", "factory", "reset_pc", "execute", "delete")):
        if t in ("powershell_tool", "powershell_cmd", "file_manager", "file_controller"):
            return True
        if any(k in a for k in ("shutdown", "restart", "wipe", "factory", "reset_pc")):
            return True
    if t in ("computer_settings", "computer_control", "desktop_control") and a in CRITICAL_ACTIONS:
        return True
    return False


def require_owner(
    tool_name: str = "",
    action: str = "",
    *,
    method: str = "any",
    password: str | None = None,
    voice_path=None,
    image_path=None,
    camera: bool = False,
    text: str | None = None,
    **_kwargs,
) -> dict:
    """Authorize critical actions via master password (default 123gui834).

    Protocolo 190 must NOT call this. Legacy biometric args are ignored unless
    password is absent and biometrics modules still succeed (best-effort).
    """
    cand = password or extract_password_from_text(text) or extract_password_from_text(action)
    if password_ok(cand):
        try:
            from core import audit
            audit.log_event("owner_password_ok", tool=tool_name or "owner_gate", extra={"action": action})
        except Exception:
            pass
        return {"ok": True, "method": "password", "detail": "master password accepted"}
    # Legacy biometric attempt only if explicitly requested
    if method in ("face", "voice", "any") and (voice_path or image_path or camera):
        try:
            if voice_path:
                r = verify_voice(voice_path)
                if r.get("ok"):
                    return r
            if image_path or camera:
                r = verify_face(image_path, camera=camera)
                if r.get("ok"):
                    return r
        except Exception as e:
            return {"ok": False, "method": method, "detail": f"biometrics unavailable: {e}"}
    return {
        "ok": False,
        "method": "password",
        "detail": "senha mestra inválida ou ausente (JARVIS_MASTER_PASSWORD / 123gui834)",
    }



def enrollment_prompt_pt() -> str:
    st = enrollment_status()
    missing = []
    if not st["voice"]:
        missing.append("vozdono.mp3 (sua voz dizendo o comando, ex: “ok jarvis”)")
    if not st["faces_ok"]:
        for name, ok in st["faces"].items():
            if not ok:
                label = {
                    "fotobase1.jpg": "frente",
                    "fotobase2.jpg": "lado esquerdo",
                    "fotobase3.jpg": "lado direito",
                }.get(name, name)
                missing.append(f"{name} (rosto de {label})")
    if not st["phrase"]:
        missing.append("frase de comando do dono")
    if not missing:
        return "Cadastro do dono completo."
    return (
        "Primeira inicialização: preciso cadastrar o dono antes de ações críticas. "
        "Falta: " + "; ".join(missing) + ". "
        "Use a tool `owner_setup` ou coloque os arquivos em memory/biometrics/."
    )

# ── Session lock / inactivity (Stage 2) ───────────────────────────────────────

_DEFAULT_IDLE_SEC = int(os.environ.get("MARK_SESSION_IDLE_SEC", "900"))  # 15 min
_lock_state = {
    "last_activity": time.time(),
    "locked": False,
    "idle_sec": _DEFAULT_IDLE_SEC,
}
_lock_mu = threading.RLock()


def configure_idle_timeout(seconds: int) -> None:
    with _lock_mu:
        _lock_state["idle_sec"] = max(60, int(seconds))


def touch_activity() -> None:
    """Call on successful user interaction / speech / unlock."""
    with _lock_mu:
        _lock_state["last_activity"] = time.time()
        _lock_state["locked"] = False


def lock_session(reason: str = "manual") -> None:
    with _lock_mu:
        _lock_state["locked"] = True
    try:
        from core import audit
        audit.log_event("session_locked", {"reason": reason})
    except Exception:
        pass


def is_session_locked() -> bool:
    with _lock_mu:
        idle = _lock_state["idle_sec"]
        last = _lock_state["last_activity"]
        if _lock_state["locked"]:
            return True
        if (time.time() - last) >= idle:
            _lock_state["locked"] = True
            return True
        return False


def session_status() -> dict[str, Any]:
    with _lock_mu:
        idle_for = time.time() - _lock_state["last_activity"]
        locked = bool(_lock_state["locked"] or (idle_for >= _lock_state["idle_sec"]))
        if locked:
            _lock_state["locked"] = True
        return {
            "locked": locked,
            "idle_for_sec": round(idle_for, 1),
            "idle_limit_sec": _lock_state["idle_sec"],
            "last_activity": _lock_state["last_activity"],
        }


def unlock_with_face(*, threshold: Optional[float] = None, password: str | None = None) -> dict[str, Any]:
    if password_ok(password):
        return {"ok": True, "method": "password"}
    # biometrics disabled at boot — password required
    return {"ok": False, "method": "password", "detail": "use master password"}

def unlock_with_face_legacy(*, threshold: Optional[float] = None) -> dict[str, Any]:
    """Quick face revalidation (with liveness) to clear session lock."""
    from core import face_auth
    try:
        score = face_auth.verify_from_camera(threshold=threshold, require_liveness=True)
        accepted = bool(score.accepted)
        if accepted:
            touch_activity()
        result = {
            "accepted": accepted,
            "score": score.score,
            "threshold": score.threshold,
            "detail": score.detail,
            "method": "face_liveness",
        }
        try:
            from core import audit
            audit.log_event("session_unlock_face", result)
        except Exception:
            pass
        return result
    except Exception as e:
        return {"accepted": False, "detail": str(e), "method": "face_liveness"}


def require_unlocked_for_critical(
    tool_name: str = "",
    action: str = "",
    *,
    camera: bool = True,
) -> dict[str, Any]:
    """If session locked or tool is critical, demand face revalidation with liveness."""
    critical = is_critical(tool_name, action)
    locked = is_session_locked()
    if not locked and not critical:
        touch_activity()
        return {"accepted": True, "detail": "ok", "locked": False, "critical": critical}
    if needs_enrollment():
        return {"accepted": False, "detail": "enrollment_required", "critical": critical, "locked": locked}
    r = unlock_with_face() if camera else require_owner(method="face", camera=True)
    if r.get("accepted"):
        touch_activity()
    r = dict(r)
    r["critical"] = critical
    r["locked"] = locked
    return r

