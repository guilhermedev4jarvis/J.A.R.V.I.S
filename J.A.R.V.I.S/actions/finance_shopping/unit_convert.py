"""
Action: unit_convert — length, mass, temperature, volume, speed, data size.

Pure arithmetic, no network. Unknown units return ask/failed, never a guess.
"""
from __future__ import annotations

from core import outcome

# Canonical factor to SI (or bit for data). Temperature is special-cased.
_LENGTH = {  # → metres
    "m": 1.0, "meter": 1.0, "metre": 1.0, "meters": 1.0, "metres": 1.0,
    "km": 1000.0, "kilometer": 1000.0, "kilometre": 1000.0, "kilometers": 1000.0,
    "cm": 0.01, "centimeter": 0.01, "centimetre": 0.01,
    "mm": 0.001, "millimeter": 0.001,
    "mi": 1609.344, "mile": 1609.344, "miles": 1609.344,
    "yd": 0.9144, "yard": 0.9144, "yards": 0.9144,
    "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
    "in": 0.0254, "inch": 0.0254, "inches": 0.0254,
    "nmi": 1852.0, "nautical_mile": 1852.0,
}
_MASS = {  # → kilograms
    "kg": 1.0, "kilogram": 1.0, "kilograms": 1.0,
    "g": 0.001, "gram": 0.001, "grams": 0.001,
    "mg": 1e-6, "milligram": 1e-6,
    "lb": 0.45359237, "lbs": 0.45359237, "pound": 0.45359237, "pounds": 0.45359237,
    "oz": 0.028349523125, "ounce": 0.028349523125, "ounces": 0.028349523125,
    "t": 1000.0, "tonne": 1000.0, "ton": 1000.0, "tons": 1000.0,
}
_VOLUME = {  # → litres
    "l": 1.0, "liter": 1.0, "litre": 1.0, "liters": 1.0, "litres": 1.0,
    "ml": 0.001, "milliliter": 0.001, "millilitre": 0.001,
    "gal": 3.785411784, "gallon": 3.785411784, "gallons": 3.785411784,  # US
    "qt": 0.946352946, "quart": 0.946352946,
    "cup": 0.2365882365,
    "fl_oz": 0.0295735295625, "floz": 0.0295735295625,
    "m3": 1000.0, "cubic_meter": 1000.0,
}
_SPEED = {  # → m/s
    "mps": 1.0, "m/s": 1.0,
    "kph": 1000.0 / 3600.0, "km/h": 1000.0 / 3600.0, "kmh": 1000.0 / 3600.0,
    "mph": 1609.344 / 3600.0,
    "knot": 1852.0 / 3600.0, "knots": 1852.0 / 3600.0, "kt": 1852.0 / 3600.0,
}
_DATA = {  # → bytes (decimal SI for kB/MB; binary for KiB/MiB)
    "b": 1.0, "byte": 1.0, "bytes": 1.0,
    "kb": 1000.0, "kilobyte": 1000.0,
    "mb": 1e6, "megabyte": 1e6,
    "gb": 1e9, "gigabyte": 1e9,
    "tb": 1e12, "terabyte": 1e12,
    "kib": 1024.0, "mib": 1024.0 ** 2, "gib": 1024.0 ** 3, "tib": 1024.0 ** 4,
}
_TEMP = {"c", "celsius", "f", "fahrenheit", "k", "kelvin"}

_TABLES = (
    ("length", _LENGTH),
    ("mass", _MASS),
    ("volume", _VOLUME),
    ("speed", _SPEED),
    ("data", _DATA),
)


def _norm(unit: str) -> str:
    u = (unit or "").strip().lower().replace(" ", "_")
    # common aliases
    aliases = {
        "metres": "m", "meters": "m", "°c": "c", "°f": "f",
        "c°": "c", "f°": "f", "kmh": "km/h", "kph": "km/h",
    }
    return aliases.get(u, u)


def _to_celsius(value: float, unit: str) -> float:
    u = _norm(unit)
    if u in ("c", "celsius"):
        return value
    if u in ("f", "fahrenheit"):
        return (value - 32.0) * 5.0 / 9.0
    if u in ("k", "kelvin"):
        return value - 273.15
    raise ValueError(f"unknown temperature unit '{unit}'")


def _from_celsius(c: float, unit: str) -> float:
    u = _norm(unit)
    if u in ("c", "celsius"):
        return c
    if u in ("f", "fahrenheit"):
        return c * 9.0 / 5.0 + 32.0
    if u in ("k", "kelvin"):
        return c + 273.15
    raise ValueError(f"unknown temperature unit '{unit}'")


def _find_table(unit: str):
    u = _norm(unit)
    if u in _TEMP:
        return "temperature", None
    for name, table in _TABLES:
        if u in table:
            return name, table
    return None, None


def _fmt(n: float) -> str:
    if abs(n) >= 1000 or (abs(n) < 0.01 and n != 0):
        return f"{n:.6g}"
    text = f"{n:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def unit_convert(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    raw_value = params.get("value")
    frm = params.get("from_unit") or params.get("from") or ""
    to = params.get("to_unit") or params.get("to") or ""

    if raw_value is None or frm == "" or to == "":
        return outcome.ask(
            "unit_convert",
            "Which value and units should I convert (for example 72 f to c)?",
        )

    try:
        value = float(str(raw_value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return outcome.failed(
            "unit_convert",
            f"'{raw_value}' is not a number",
            value=str(raw_value),
        )

    frm_n, to_n = _norm(str(frm)), _norm(str(to))
    kind_from, table_from = _find_table(frm_n)
    kind_to, table_to = _find_table(to_n)

    if kind_from is None:
        return outcome.failed("unit_convert", f"unknown unit '{frm}'", from_unit=str(frm))
    if kind_to is None:
        return outcome.failed("unit_convert", f"unknown unit '{to}'", to_unit=str(to))
    if kind_from != kind_to:
        return outcome.failed(
            "unit_convert",
            f"cannot convert {kind_from} to {kind_to}",
            from_unit=str(frm),
            to_unit=str(to),
        )

    try:
        if kind_from == "temperature":
            result = _from_celsius(_to_celsius(value, frm_n), to_n)
        else:
            si = value * table_from[frm_n]
            result = si / table_to[to_n]
    except Exception as e:
        return outcome.failed("unit_convert", str(e))

    return outcome.done(
        "unit_convert",
        value=value,
        from_unit=frm_n,
        to_unit=to_n,
        result=_fmt(result),
        category=kind_from,
    )


TOOL = {
    "name": "unit_convert",
    "description": (
        "Converts a numeric value between units: length (m, km, mi, ft, in…), "
        "mass (kg, g, lb, oz…), temperature (C, F, K), volume (L, mL, gal…), "
        "speed (km/h, mph, knot…), and data size (KB, MB, GiB…). "
        "Use when the user asks to convert units or 'how many X in Y'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "value": {
                "type": "NUMBER",
                "description": "The numeric quantity to convert.",
            },
            "from_unit": {
                "type": "STRING",
                "description": "Source unit, e.g. 'km', 'f', 'lb'.",
            },
            "to_unit": {
                "type": "STRING",
                "description": "Target unit, e.g. 'mi', 'c', 'kg'.",
            },
        },
        "required": ["value", "from_unit", "to_unit"],
    },
    "handler": unit_convert,
}
