"""Reconhecimento facial de confiança a partir de memory/familia/."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

_BASE = Path(__file__).resolve().parents[2]
_FAM = _BASE / "memory" / "familia"

try:
    from core.event_bus import publish as _eb_pub
except Exception:
    def _eb_pub(*_a, **_k):
        pass


def _role_from_name(name: str) -> str:
    low = name.lower()
    if "mae" in low or "mãe" in low:
        return "mae"
    if "dono" in low or "owner" in low or "guilherme" in low:
        return "owner"
    return "familia"


def list_family_refs() -> list[dict]:
    refs = []
    if not _FAM.is_dir():
        return refs
    for p in sorted(_FAM.iterdir()):
        if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        if p.name.upper().startswith("README"):
            continue
        stem = p.stem
        # mae_1, dono, fotobase → name
        name = re.sub(r"[_-]?\d+$", "", stem)
        refs.append({"path": str(p), "person_name": name, "role": _role_from_name(name)})
    return refs


def recognize_face_in_frame(png_bytes: bytes, zone: str = "porta_interna") -> Optional[dict]:
    """Best-effort match against memory/familia using face_auth if available."""
    refs = list_family_refs()
    if not refs or not png_bytes:
        return None
    # Try core.face_auth verify against each ref
    try:
        from core import face_auth
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(png_bytes)
            probe = tmp.name
        for ref in refs:
            try:
                if hasattr(face_auth, "compare_images"):
                    r = face_auth.compare_images(ref["path"], probe)
                    ok = bool(r.get("ok") or r.get("match") or (r.get("score") or 0) > 0.55)
                elif hasattr(face_auth, "verify"):
                    r = face_auth.verify(probe, ref["path"])
                    ok = bool(r.get("ok") or r.get("match"))
                else:
                    ok = False
                    r = {}
                if ok:
                    result = {
                        "person_name": ref["person_name"],
                        "role": ref["role"],
                        "zone": zone,
                        "score": r.get("score"),
                    }
                    _eb_pub("vision.known_face_detected", **result)
                    return result
            except Exception:
                continue
    except Exception:
        # Fallback: filename-based soft match when only one family member labeled
        if len(refs) == 1:
            result = {"person_name": refs[0]["person_name"], "role": refs[0]["role"], "zone": zone, "score": 0.0, "soft": True}
            return result
    return None


def welcome_summary(person_name: str) -> str:
    try:
        from core.event_bus import recent_events
        evs = recent_events(15)
        parts = []
        for e in evs[-8:]:
            et = e.get("event") or ""
            if et.startswith("power.") or et.startswith("wifi.") or et.startswith("alpr."):
                parts.append(et)
        if parts:
            return "Enquanto esteve fora: " + ", ".join(parts[-5:])
    except Exception:
        pass
    try:
        from core import audit as audit_mod
        if hasattr(audit_mod, "recent"):
            rec = audit_mod.recent(10)
            return f"{len(rec)} eventos de auditoria recentes."
    except Exception:
        pass
    return "Nada crítico registrado."
