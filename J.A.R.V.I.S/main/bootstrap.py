"""Process-level bootstrap: Windows silent subprocess + UTF-8 console.

Imported once from main package init; must stay side-effect light and safe under
pythonw / redirected pipes.
"""
from __future__ import annotations

import platform as _platform
import subprocess as _subprocess
import sys as _sys

def apply() -> None:
    """Apply OS-level patches. Idempotent."""
    if getattr(apply, "_done", False):
        return
    if _platform.system() == "Windows":
        _OrigPopen = _subprocess.Popen

        class _Popen(_OrigPopen):
            def __init__(self, args, **kw):
                kw["creationflags"] = kw.get("creationflags", 0) | _subprocess.CREATE_NO_WINDOW
                kw.pop("startupinfo", None)
                super().__init__(args, **kw)

        _subprocess.Popen = _Popen  # type: ignore[misc, assignment]

    for _stream in ("stdout", "stderr"):
        try:
            _s = getattr(_sys, _stream, None)
            if _s is not None and hasattr(_s, "reconfigure"):
                _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    apply._done = True  # type: ignore[attr-defined]

apply()
