"""Sanity: all public actions load; TOOL name matches filename; identity MARK LXI."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ACTIONS = sorted(
    {
        p.stem
        for p in (ROOT / "actions").rglob("*.py")
        if not p.name.startswith("_") and p.name != "__init__.py"
        and "__pycache__" not in p.parts
    }
)

def _module_for(stem: str) -> str:
    for p in (ROOT / "actions").rglob(f"{stem}.py"):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(ROOT / "actions")
        return "actions." + ".".join(rel.with_suffix("").parts)
    return f"actions.{stem}"

# Modules that intentionally have no TOOL (engines / helpers colocated under actions/)
NO_TOOL_OK = {"proactive", "screen_processor"}


@pytest.mark.parametrize("stem", ACTIONS)
def test_action_importable(stem):
    mod = importlib.import_module(_module_for(stem))
    assert mod is not None


@pytest.mark.parametrize("stem", [s for s in ACTIONS if s not in NO_TOOL_OK])
def test_tool_name_matches_filename(stem):
    mod = importlib.import_module(_module_for(stem))
    tool = getattr(mod, "TOOL", None)
    assert tool is not None, f"{stem} missing TOOL"
    assert tool.get("name") == stem
    assert callable(tool.get("handler"))


def test_identity_synced():
    from core.product import PRODUCT_NAME, ARMOR_MARK
    assert PRODUCT_NAME == "J.A.R.V.I.S."
    assert "LXI" in ARMOR_MARK

    for rel in ("README.md", "LICENSE", "ui/app.py", "core/prompt.txt"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "MARK LVI" not in text or rel.endswith(".md") and False  # hard fail on LVI
        assert "MARK LVI" not in text

    assert "MARK LXI" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Guilherme" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert "J.A.R.V.I.S" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_no_obsolete_cache_tests():
    assert not (ROOT / "cache" / "code_forge" / "test_broken.py").exists()
    assert not (ROOT / "cache" / "code_forge" / "test_ok.py").exists()
    assert not (ROOT / "updates" / "proposals" / "20261013_170035_monitor_tool.json").exists()


def test_api_key_preserved():
    # Public package must not ship live secrets; only templates.
    assert not (ROOT / ".env").exists()
    example = ROOT / ".env.example"
    assert example.is_file() or (ROOT / "config" / "api_keys.json.example").is_file()
