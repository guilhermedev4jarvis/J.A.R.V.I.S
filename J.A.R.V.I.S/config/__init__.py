# config/__init__.py
import json, os, platform
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "api_keys.json"

def _platform_os() -> str:
    """Auto-detect OS when config file is absent."""
    return {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}.get(
        platform.system(), "linux"
    )

def get_config() -> dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def get_os() -> str:
    """Returns: 'windows' | 'mac' | 'linux'.

    ``os_system: "auto"`` (the default in api_keys.json) means "detect from the
    running machine". Returning the literal string ``"auto"`` made every
    ``is_windows()`` / ``is_mac()`` / ``is_linux()`` check fail, so Steam paths,
    flight-finder shortcuts and any other OS branch silently took the wrong arm.
    """
    configured = (get_config().get("os_system") or "auto").strip().lower()
    if configured in ("", "auto"):
        return _platform_os()
    if configured in ("windows", "mac", "linux"):
        return configured
    # Unknown value — fall back to detection rather than break all OS checks.
    return _platform_os()

def is_windows() -> bool: return get_os() == "windows"
def is_mac()     -> bool: return get_os() == "mac"
def is_linux()   -> bool: return get_os() == "linux"
