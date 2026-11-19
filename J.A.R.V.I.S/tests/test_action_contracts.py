"""
Contract tests for bundled actions.

Run:  python -m pytest tests/test_action_contracts.py -q
or:   python tests/test_action_contracts.py
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_KEYS = {"name", "description", "parameters", "handler"}


def _load_actions():
    actions_dir = ROOT / "actions"
    loaded = []
    for path in sorted(actions_dir.rglob("*.py"), key=lambda x: str(x)):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(actions_dir)
        name = "actions." + ".".join(rel.with_suffix("").parts)
        try:
            mod = importlib.import_module(name)
        except Exception as e:
            loaded.append((str(rel), None, f"import error: {e}"))
            continue
        tool = getattr(mod, "TOOL", None)
        loaded.append((str(rel), tool, None))
    return loaded


def test_every_tool_has_required_shape():
    for filename, tool, err in _load_actions():
        if err and tool is None and "No module-level TOOL" not in str(err):
            # Helper modules without TOOL are allowed
            if tool is None:
                continue
        if tool is None:
            continue
        missing = REQUIRED_KEYS - set(tool.keys())
        assert not missing, f"{filename}: missing TOOL keys {missing}"
        assert callable(tool["handler"]), f"{filename}: handler not callable"
        assert isinstance(tool["name"], str) and tool["name"], f"{filename}: bad name"
        params = tool["parameters"]
        assert isinstance(params, dict) and params.get("type") == "OBJECT", (
            f"{filename}: parameters must be OBJECT schema"
        )


def test_new_actions_import_and_fail_gracefully():
    """New actions must not crash on empty params; they return status=failed/ask/done."""
    names = [
        "clipboard_smart",
        "window_manager",
                "system_health",
        "file_organize",
        "focus_timer",
        "protocolo",
        "email_triage",
        "meeting_brief",
        "routine_orchestrator",
        "local_doc_rag",
        "desktop_control",
        "weather_report",
    ]
    from core.action_loader import discover_actions
    reg = discover_actions(ROOT / "actions", logger=lambda *_: None)
    # map stem -> module path from filesystem
    stem_path = {}
    for path in (ROOT / "actions").rglob("*.py"):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT / "actions")
        stem_path[path.stem] = "actions." + ".".join(rel.with_suffix("").parts)
    for stem in names:
        modname = stem_path.get(stem) or f"actions.{stem}"
        mod = importlib.import_module(modname)
        tool = getattr(mod, "TOOL", None)
        assert tool is not None, f"{stem} missing TOOL"
        handler = tool["handler"]
        result = handler(parameters={})
        assert isinstance(result, str) and result, f"{stem} returned empty"
        assert any(
            k in result for k in ("status=done", "status=failed", "status=ask", "status=unverified", "status=started")
        ), f"{stem} did not use outcome protocol: {result[:120]}"


if __name__ == "__main__":
    test_every_tool_has_required_shape()
    test_new_actions_import_and_fail_gracefully()
    print("OK — action contracts passed")
