"""UI theme, palette, layout constants and pure geometry helpers."""
from __future__ import annotations

import json
import math
import os
import platform
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from PyQt6.QtGui import QColor
except Exception:  # pragma: no cover
    QColor = None  # type: ignore

# Package at <root>/ui/*.py → project root is parents[1]
def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]

BASE_DIR = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE = CONFIG_DIR / "api_keys.json"

APP_NAME = "J.A.R.V.I.S."
APP_AUTHOR = "Guilherme"
APP_VERSION = "MARK LXI"
APP_PROTOCOL = APP_VERSION.split()[-1]

_DEFAULT_W, _DEFAULT_H = 1100, 720
_MIN_W, _MIN_H = 820, 580
_LEFT_W = 148
_RIGHT_W = 340
_OS = platform.system()

class C:
    BG        = "#050301"
    PANEL     = "#0c0906"
    PANEL2    = "#17100a"
    BORDER    = "#382717"
    BORDER_B  = "#8a5728"
    BORDER_A  = "#65401e"
    PRI       = "#ff9b2f"
    PRI_DIM   = "#995d27"
    PRI_GHO   = "#281806"
    ACC       = "#f59030"
    ACC2      = "#ffd18a"
    GREEN     = "#ffb45b"
    GREEN_D   = "#a6652a"
    RED       = "#ff8531"
    MUTED_C   = "#c9702a"
    TEXT      = "#ffe3c4"
    TEXT_DIM  = "#a77e56"
    TEXT_MED  = "#d09a65"
    WHITE     = "#fff0df"
    DARK      = "#100a04"
    BAR_BG    = "#1b1209"

    # Kept outside the monochrome palette for a few semantic status/action texts.
    TEXT_GOOD = "#66df91"
    TEXT_INFO = "#70cfff"
    TEXT_BAD  = "#ff7373"


# The base interface palette shares the selected accent hue. A few semantic text
# colors below are reserved for listening, progress and cancel/error states.
_HUE_LINKED = (
    "BG", "PANEL", "PANEL2", "BORDER", "BORDER_B", "BORDER_A",
    "PRI", "PRI_DIM", "PRI_GHO", "ACC", "ACC2", "GREEN", "GREEN_D",
    "RED", "MUTED_C", "TEXT", "TEXT_DIM", "TEXT_MED", "WHITE", "DARK",
    "BAR_BG",
)
_PALETTE_DEFAULTS: dict[str, str] = {k: getattr(C, k) for k in _HUE_LINKED}

DEFAULT_UI_COLOR = _PALETTE_DEFAULTS["PRI"]


def apply_ui_accent(accent_hex: str) -> bool:
    """
    Re-derives the full monochrome palette from the chosen accent hue. The
    selected color stays exact; supporting shades keep their contrast levels.
    """
    import colorsys

    accent_hex = (accent_hex or "").strip().lower()
    if not (accent_hex.startswith("#") and len(accent_hex) == 7):
        return False
    try:
        int(accent_hex[1:], 16)
    except ValueError:
        return False

    def _hsv(h: str) -> tuple[float, float, float]:
        r = int(h[1:3], 16) / 255
        g = int(h[3:5], 16) / 255
        b = int(h[5:7], 16) / 255
        return colorsys.rgb_to_hsv(r, g, b)

    acc_h, acc_s, _av = _hsv(accent_hex)
    _base_s = _hsv(_PALETTE_DEFAULTS["PRI"])[1]
    sat_scale = min(1.0, acc_s / max(0.01, _base_s))

    for key, hex0 in _PALETTE_DEFAULTS.items():
        if key == "PRI":
            setattr(C, key, accent_hex)
            continue
        _h, s, v = _hsv(hex0)
        r, g, b = colorsys.hsv_to_rgb(acc_h, min(1.0, s * sat_scale), v)
        setattr(C, key, "#{:02x}{:02x}{:02x}".format(
            int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)))
    return True


# Normalize the startup palette too, so its status lights and text start in
# the same hue before a saved custom color is loaded.
apply_ui_accent(DEFAULT_UI_COLOR)


def current_palette() -> dict[str, str]:
    """A snapshot of the accent-linked colours currently on class C."""
    return {k: getattr(C, k) for k in _HUE_LINKED}


def retheme_all_widgets(old: dict[str, str], new: dict[str, str]) -> None:
    """
    LIVE full theme change. Replaces the old palette colours with the new ones
    in EVERY widget's stylesheet across the app and repaints them. This way the
    colour change applies INSTANTLY across the whole interface — panels, buttons,
    borders included — not just the painted elements. No restart needed.
    """
    mapping = {old[k].lower(): new[k].lower()
               for k in old if old[k].lower() != new.get(k, old[k]).lower()}
    if not mapping:
        return
    app = QApplication.instance()
    if app is None:
        return
    painted = {"HudCanvas", "MetricBar", "HueWheel", "_DropCanvas"}
    # Replace every old shade in a single pass. Sequential str.replace() calls
    # can recolor a newly inserted value again when it matches another old
    # palette entry.
    color_pattern = re.compile(
        "|".join(re.escape(color) for color in sorted(mapping, key=len, reverse=True)),
        re.IGNORECASE,
    )
    for w in app.allWidgets():
        try:
            ss = w.styleSheet()
            changed = False
            if ss:
                s2 = color_pattern.sub(
                    lambda match: mapping[match.group(0).lower()], ss)
                if s2 != ss:
                    w.setStyleSheet(s2)
                    changed = True
            if w.__class__.__name__ == "MetricBar":
                w._color = mapping.get(str(w._color).lower(), new["PRI"])
                changed = True
            if changed or (w.isVisible() and w.__class__.__name__ in painted):
                w.update()
        except Exception:
            pass


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c

