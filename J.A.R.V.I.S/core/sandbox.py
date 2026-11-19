"""
core/sandbox.py — dry-run context and path guards for destructive actions.

Design
------
- Dry-run is a *thread-local* flag so nested tool calls see the same mode.
- Path policy is allow-list oriented: writes outside known user roots require
  explicit confirmation (or are blocked in air-gapped / strict mode).
- This module does NOT replace core.confirm for irreversible OS actions; it
  complements it by catching file-system foot-guns earlier.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path, PureWindowsPath
from typing import Any, Optional

from core.contracts import is_destructive_action, path_params_from_args

_tls = threading.local()

# Roots that are generally safe for user-driven automation.
_SAFE_ROOT_NAMES = (
    "Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos",
    "OneDrive", "Dropbox", "Google Drive",
)


def _home() -> Path:
    return Path.home().resolve()


def allowed_roots() -> list[Path]:
    """User-facing directories plus the project itself."""
    home = _home()
    roots = [home]
    for name in _SAFE_ROOT_NAMES:
        candidate = home / name
        if candidate.is_dir():
            roots.append(candidate.resolve())
    # Project tree (actions writing into cache/memory/config are fine)
    try:
        roots.append(Path(__file__).resolve().parents[1])
    except Exception:
        pass
    # Temp
    tmp = os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp"
    try:
        roots.append(Path(tmp).resolve())
    except Exception:
        pass
    return roots


def path_is_allowed(path_str: str) -> tuple[bool, str]:
    """Return (ok, reason). ok=False means the path is outside allowed roots."""
    if not path_str or not str(path_str).strip():
        return True, "empty"
    raw = str(path_str).strip()
    # Ignore pure URLs / special tokens
    if "://" in raw or raw.lower() in {"desktop", "downloads", "documents", "home"}:
        return True, "alias_or_url"
    try:
        # Expand ~ and environment variables
        expanded = os.path.expandvars(os.path.expanduser(raw))
        target = Path(expanded).resolve()
    except Exception as e:
        return False, f"unresolvable path: {e}"

    for root in allowed_roots():
        try:
            target.relative_to(root)
            return True, f"under {root}"
        except ValueError:
            continue
        except Exception:
            continue

    # Windows drive root of home is still "user territory"
    try:
        if os.name == "nt":
            home_drive = PureWindowsPath(_home()).drive
            if PureWindowsPath(target).drive.lower() == home_drive.lower():
                # Still outside named roots — flag but allow with review
                return False, f"outside named safe roots (drive {home_drive})"
    except Exception:
        pass

    return False, f"outside allowed roots: {target}"


def set_dry_run(enabled: bool) -> None:
    _tls.dry_run = bool(enabled)


def is_dry_run() -> bool:
    return bool(getattr(_tls, "dry_run", False))


class dry_run_mode:
    """Context manager: force dry-run for the current thread."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._prev: Optional[bool] = None

    def __enter__(self):
        self._prev = getattr(_tls, "dry_run", False)
        _tls.dry_run = self.enabled
        return self

    def __exit__(self, *exc):
        _tls.dry_run = self._prev
        return None


def precheck(
    tool_name: str,
    args: dict | None,
    *,
    risk: str = "review",
    strict: bool = False,
) -> Optional[str]:
    """Return a human-readable block reason, or None if the call may proceed.

    When dry-run is active and the action is destructive, returns a synthetic
    explanation so the tool can short-circuit without side effects.
    """
    args = args or {}
    destructive = is_destructive_action(tool_name, args, risk=risk)

    if is_dry_run() and destructive:
        return (
            f"dry_run: would execute {tool_name} with {args!r} — "
            "no side effects applied"
        )

    paths = path_params_from_args(args)
    action = str(args.get("action", "")).lower()
    writing = action in {
        "delete", "remove", "rm", "write", "create", "create_file",
        "create_folder", "move", "copy", "rename", "overwrite", "organize_desktop",
    } or destructive

    if writing and paths:
        for key, val in paths.items():
            ok, reason = path_is_allowed(val)
            if not ok:
                if strict:
                    return f"blocked path {key}={val!r}: {reason}"
                # Non-strict: signal that confirm is required
                return f"path_review_required {key}={val!r}: {reason}"

    return None


def summarize_policy() -> dict[str, Any]:
    return {
        "dry_run": is_dry_run(),
        "allowed_roots": [str(p) for p in allowed_roots()],
    }
