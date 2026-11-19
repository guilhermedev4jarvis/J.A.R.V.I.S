"""
dependency_health — checks critical packages for JARVIS.

Verifies that key libraries are importable, reports installed versions,
and optionally compares against requirements.txt lower bounds.
Never installs packages automatically (that needs user confirmation /
elevated rights); it only diagnoses and suggests pip commands.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import platform
import sys
from pathlib import Path
from typing import Any

from core.outcome import done, failed, ask

_BASE = Path(__file__).resolve().parents[2]
_REQ_PATH = _BASE / "requirements.txt"

# (import_name, pip_name, why_it_matters, optional)
_CRITICAL = [
    ("psutil", "psutil", "system monitoring & process control", False),
    ("sounddevice", "sounddevice", "audio input/output", False),
    ("numpy", "numpy", "audio buffers & avatar math", False),
    ("google.genai", "google-genai", "Gemini Live API", False),
    ("httpx", "httpx", "HTTP client used by providers", False),
    ("PIL", "pillow", "screenshots & image processing", False),
    ("cv2", "opencv-python", "vision / camera / OCR helpers", True),
    ("playwright", "playwright", "browser automation", True),
    ("requests", "requests", "web requests & many actions", False),
    ("bs4", "beautifulsoup4", "HTML parsing for research/news", True),
    ("PyQt6", "PyQt6", "UI / avatar / HUD", False),
    ("yt_dlp", "yt-dlp", "YouTube stream extraction", True),
    ("pyautogui", "pyautogui", "desktop automation", True),
    ("pyperclip", "pyperclip", "clipboard access", True),
    ("mss", "mss", "fast screenshots", True),
]


def _version_of(dist_name: str) -> str | None:
    try:
        return importlib.metadata.version(dist_name)
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception:
        return None


def _can_import(import_name: str) -> tuple[bool, str | None]:
    try:
        importlib.import_module(import_name)
        return True, None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _parse_requirements_lower_bounds() -> dict[str, str]:
    """Very small parser: name>=X.Y  →  {name: X.Y}"""
    bounds: dict[str, str] = {}
    if not _REQ_PATH.exists():
        return bounds
    try:
        for line in _REQ_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip environment markers
            if ";" in line:
                line = line.split(";", 1)[0].strip()
            for op in (">=", "==", "~=", ">"):
                if op in line:
                    name, ver = line.split(op, 1)
                    name = name.strip().lower().replace("_", "-")
                    ver = ver.strip().split(",")[0].strip()
                    bounds[name] = ver
                    break
            else:
                # bare name
                bounds[line.lower().replace("_", "-")] = ""
    except Exception:
        pass
    return bounds


def dependency_health(parameters: dict | None = None, **_ctx) -> str:
    params = parameters or {}
    action = (params.get("action") or "check").strip().lower()
    include_optional = str(params.get("optional") or "true").lower() not in ("0", "false", "no")

    # ── environment ───────────────────────────────────────────────────────
    if action in ("env", "environment", "python"):
        return done(
            "dependency_health",
            action="env",
            python=sys.version.split()[0],
            platform=platform.platform(),
            executable=sys.executable,
            prefix=sys.prefix,
        )

    # ── check ─────────────────────────────────────────────────────────────
    if action in ("check", "status", "report", "health"):
        bounds = _parse_requirements_lower_bounds()
        ok_list = []
        missing = []
        broken = []
        optional_missing = []

        for import_name, pip_name, reason, optional in _CRITICAL:
            if optional and not include_optional:
                continue

            can, err = _can_import(import_name)
            ver = _version_of(pip_name)

            if can and ver:
                ok_list.append(f"{pip_name}=={ver}")
            elif can and not ver:
                ok_list.append(f"{pip_name} (import ok, version unknown)")
            elif not can:
                entry = f"{pip_name} ({reason})"
                if optional:
                    optional_missing.append(entry)
                else:
                    missing.append(entry)
                if err and "No module named" not in (err or ""):
                    broken.append(f"{pip_name}: {err}")

        # Suggest install command for missing hard deps
        hard_missing_pips = []
        for import_name, pip_name, reason, optional in _CRITICAL:
            if optional:
                continue
            can, _ = _can_import(import_name)
            if not can:
                hard_missing_pips.append(pip_name)

        suggest = ""
        if hard_missing_pips:
            suggest = "pip install " + " ".join(hard_missing_pips)

        return done(
            "dependency_health",
            action="check",
            ok_count=len(ok_list),
            missing_required=len(missing),
            missing_optional=len(optional_missing),
            broken=len(broken),
            installed="; ".join(ok_list[:20]) + ("..." if len(ok_list) > 20 else ""),
            required_missing="; ".join(missing) if missing else "none",
            optional_missing="; ".join(optional_missing) if optional_missing else "none",
            import_errors="; ".join(broken[:5]) if broken else "none",
            suggest_install=suggest or "none",
            python=sys.version.split()[0],
        )

    # ── one package ───────────────────────────────────────────────────────
    if action in ("one", "package", "info"):
        name = (params.get("name") or params.get("package") or "").strip()
        if not name:
            return ask("dependency_health", "which package?", hint="name=playwright")

        # Try both import-style and pip-style
        candidates = [name, name.replace("-", "_"), name.replace("_", "-")]
        found_import = None
        found_ver = None
        err = None

        for c in candidates:
            can, e = _can_import(c)
            if can:
                found_import = c
                break
            err = e

        for c in candidates:
            v = _version_of(c)
            if v:
                found_ver = v
                break

        if found_import or found_ver:
            return done(
                "dependency_health",
                action="one",
                name=name,
                importable=bool(found_import),
                version=found_ver or "unknown",
                import_name=found_import,
            )
        return done(
            "dependency_health",
            action="one",
            name=name,
            importable=False,
            version=None,
            error=err or "not found",
            suggest=f"pip install {name}",
        )

    # ── requirements diff (very light) ────────────────────────────────────
    if action in ("requirements", "req", "bounds"):
        bounds = _parse_requirements_lower_bounds()
        if not bounds:
            return done(
                "dependency_health",
                action="requirements",
                note="could not parse requirements.txt or file missing",
            )
        sample = list(bounds.items())[:25]
        summary = "; ".join(f"{k}>={v}" if v else k for k, v in sample)
        return done(
            "dependency_health",
            action="requirements",
            count=len(bounds),
            sample=summary,
        )

    return ask(
        "dependency_health",
        "what should I check?",
        options="check, env, one (name=...), requirements",
    )


TOOL = {
    "name": "dependency_health",
    "description": (
        "Checks whether critical Python packages for JARVIS are installed and "
        "importable (psutil, sounddevice, google-genai, PyQt6, playwright, etc.). "
        "Reports versions, missing required/optional deps and suggests pip install "
        "commands. Does NOT install anything by itself. "
        "Actions: check (full report), env (Python/platform info), "
        "one (name=package), requirements (parsed lower bounds)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "check | env | one | requirements",
            },
            "name": {
                "type": "STRING",
                "description": "Package name for action=one",
            },
            "optional": {
                "type": "STRING",
                "description": "Include optional packages in check (default true)",
            },
        },
        "required": [],
    },
    "handler": dependency_health,
    "tier": "core",
}
