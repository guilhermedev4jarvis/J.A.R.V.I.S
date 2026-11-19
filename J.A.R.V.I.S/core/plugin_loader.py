"""
core/plugin_loader.py — DEPRECATED compatibility shim.

As of the unified architecture, all tools live under actions/ and are loaded by
core.action_loader.discover_actions(). This module remains importable so older
scripts do not crash, but it no longer scans plugins/ for live TOOL/PLUGIN
declarations.

Migration: put new tools in actions/*.py with a TOOL dict + handler.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

_WARNED = False


def _warn_once() -> None:
    global _WARNED
    if not _WARNED:
        warnings.warn(
            "core.plugin_loader is deprecated; use core.action_loader / actions/*.py",
            DeprecationWarning,
            stacklevel=3,
        )
        _WARNED = True
        print("[Plugins] DEPRECATION: plugin_loader is a no-op shim — tools load from actions/")


@dataclass
class PluginRecord:
    name: str
    valid: bool = False
    path: Optional[Path] = None
    description: str = ""
    run: Optional[Callable] = None
    scheduling: Optional[str] = None
    tier: Optional[str] = None
    brief: Optional[str] = None
    settings: Optional[dict] = None
    error: str = "deprecated — use actions/"


class PluginRegistry:
    """Empty registry kept for main.py attribute compatibility."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginRecord] = {}

    def names(self) -> set[str]:
        return set()

    def get_tool_declarations(self) -> list[dict]:
        return []

    def has(self, name: str) -> bool:
        return False

    def scheduling(self, name: str) -> Optional[str]:
        return None

    def run(self, name: str, parameters: dict, player=None, session_memory=None) -> str:
        return (
            f"Plugin '{name}' is no longer loaded from plugins/. "
            f"Use the unified action with the same name under actions/."
        )

    def list_for_ui(self) -> list[dict]:
        return []

    def settings_schemas(self) -> list[dict]:
        return []


def discover_plugins(
    plugins_dir: Path | None = None,
    core_tool_names: set[str] | None = None,
    logger: Optional[Callable[[str], None]] = None,
    notify: Optional[Callable[[str], None]] = None,
) -> PluginRegistry:
    _warn_once()
    if logger:
        logger("shim active — zero plugins loaded; all tools come from actions/")
    return PluginRegistry()


# Back-compat aliases some scripts may import
def get_plugin_enabled(name: str) -> bool:
    return False
