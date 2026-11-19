from __future__ import annotations
import os, platform
from pathlib import Path
from typing import Any, Optional

_BASE = Path(__file__).resolve().parents[1]

def candidate_paths():
    out, seen = [], set()
    def add(p):
        if not p: return
        path = Path(p)
        k = str(path).lower()
        if k in seen: return
        seen.add(k); out.append(path)
    for k in ("VSM_APP_PATH", "VMS_APP_PATH", "ICSEE_APP_PATH"):
        add((os.environ.get(k) or "").strip())
    for base in (_BASE, _BASE.parent, Path.cwd()):
        add(base / "VSM" / "VSM.exe")
        add(base / "VSM.exe")
    return out

def resolve_vsm():
    for p in candidate_paths():
        try:
            if p.is_file(): return p.resolve()
        except Exception:
            pass
    return None

def run_health_check(*, try_launch: bool = True):
    path = resolve_vsm()
    if path is None:
        return {"ok": False, "message": "VSM/VSM.exe nao encontrado", "candidates": candidate_paths()[:8]}
    size = path.stat().st_size
    if size <= 0:
        return {"ok": False, "message": f"VSM zero bytes: {path}", "resolved_path": str(path)}
    return {"ok": True, "message": f"VSM arquivo OK — {path}", "resolved_path": str(path), "candidates": candidate_paths()[:8]}

def log_and_notify(ui=None):
    r = run_health_check(try_launch=True)
    print("[VSM_HEALTH]", r.get("message"))
    return r
