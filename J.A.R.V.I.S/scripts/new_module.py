#!/usr/bin/env python3
"""Scaffold a new unified action (TOOL contract under actions/).

Examples:
  python scripts/new_module.py weather_now
  python scripts/new_module.py action stock_quote --desc "Cotação de ação"
  python scripts/new_module.py my_tool --risk safe

The legacy `plugin` subcommand still works but writes into actions/ with a note.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

ACTION_TEMPLATE = '''"""
{name} — {description}
"""
from __future__ import annotations

from core.outcome import done, failed, ask


def {name}(parameters: dict | None = None, **_ctx) -> str:
    params = parameters or {{}}
    action = str(params.get("action") or "run").strip().lower()

    if action in ("status", "help"):
        return done("{name}", action="status", note="ready")

    value = params.get("value") or params.get("query") or ""
    if not value and action == "run":
        return ask("{name}", "what should I do?", hint="pass value=...")

    try:
        result = f"handled {{value!r}}"
        return done("{name}", action=action or "run", result=result)
    except Exception as e:
        return failed("{name}", str(e))


TOOL = {{
    "name": "{name}",
    "description": (
        "{description}"
    ),
    "parameters": {{
        "type": "OBJECT",
        "properties": {{
            "action": {{"type": "STRING", "description": "status | run"}},
            "value": {{"type": "STRING", "description": "Main argument"}},
            "query": {{"type": "STRING", "description": "Alias for value"}},
        }},
        "required": [],
    }},
    "handler": {name},
    "tier": "core",
    "risk": "{risk}",
}}
'''


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Create a new JARVIS action module")
    p.add_argument(
        "kind",
        nargs="?",
        default="action",
        help="action (default) | plugin (deprecated alias → still writes actions/)",
    )
    p.add_argument("name", nargs="?", help="module name snake_case")
    p.add_argument("--desc", default="New unified tool", help="TOOL description")
    p.add_argument(
        "--risk",
        default="review",
        choices=("safe", "review", "destructive", "autonomous"),
    )
    args = p.parse_args(argv)

    # Allow: python new_module.py my_name
    if args.kind not in ("action", "plugin") and args.name is None:
        args.name = args.kind
        args.kind = "action"

    if not args.name or not NAME_RE.match(args.name):
        print("Name must match ^[a-z][a-z0-9_]{0,63}$")
        return 2

    if args.kind == "plugin":
        print(
            "[new_module] WARNING: plugins/ is deprecated. "
            "Writing unified action under actions/ instead."
        )

    dest = ROOT / "actions" / f"{args.name}.py"
    if dest.exists():
        print(f"Already exists: {dest}")
        return 1

    dest.write_text(
        ACTION_TEMPLATE.format(
            name=args.name,
            description=args.desc.replace('"', "'"),
            risk=args.risk,
        ),
        encoding="utf-8",
    )
    print(f"Created {dest.relative_to(ROOT)}")
    print("Restart JARVIS or hot-reload to pick it up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
