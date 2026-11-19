from __future__ import annotations

import importlib
import json
import sys
from types import SimpleNamespace

import pytest


class _FakeLocator:
    def __init__(self) -> None:
        self.filled = []

    def fill(self, value: str) -> None:
        self.filled.append(value)

    def click(self) -> None:
        return None

    def inner_text(self, timeout: int = 8000) -> str:
        return "Conteudo principal\nMenu"


class _FakePage:
    def __init__(self) -> None:
        self.url = "https://example.com"
        self._locator = _FakeLocator()
        self._keyboard = SimpleNamespace(press=lambda key: None)

    @property
    def keyboard(self):
        return self._keyboard

    def goto(self, url: str, wait_until: str, timeout: int) -> None:
        self.url = url

    def title(self) -> str:
        return "Example"

    def evaluate(self, script, *args):
        if "Array.from" in script:
            return [
                {"title": "Docs", "href": "https://example.com/docs"},
                {"title": "Home", "href": "https://example.com"},
            ]
        return None

    def locator(self, selector: str):
        return self._locator

    def wait_for_timeout(self, milliseconds: int) -> None:
        return None


class _FakeBrowser:
    def new_page(self):
        return _FakePage()

    def close(self) -> None:
        return None


class _FakePlaywright:
    chromium = SimpleNamespace(launch=lambda headless=True: _FakeBrowser())

    def start(self):
        return self

    def stop(self) -> None:
        return None


def test_browser_pilot_missing_playwright(monkeypatch):
    import actions.browser_pilot as mod

    monkeypatch.setattr(mod.importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError(name)))
    result = mod.handler({"action": "extract_links", "url": "https://example.com"})
    assert "status=failed" in result
    assert "pip install playwright" in result


def test_browser_pilot_extract_links_mocked(monkeypatch):
    import actions.browser_pilot as mod

    monkeypatch.setattr(mod, "_load_playwright", lambda: SimpleNamespace(
        sync_playwright=lambda: _FakePlaywright(),
    ))
    result = mod.handler({"action": "extract_links", "url": "https://example.com"})
    assert "status=done" in result
    assert "Docs" in result
    assert "https://example.com/docs" in result


def test_browser_pilot_fill_requires_confirmation(monkeypatch):
    import actions.browser_pilot as mod

    monkeypatch.setattr(mod, "_load_playwright", lambda: SimpleNamespace(
        sync_playwright=lambda: _FakePlaywright(),
    ))
    result = mod.handler({
        "action": "fill_and_submit",
        "url": "https://example.com/form",
        "fields": {"#q": "jarvis"},
        "submit": True,
    })
    assert "status=ask" in result


def test_habit_miner_analyze_and_suggest(tmp_path):
    import actions.habit_miner as mod

    memory = tmp_path / "memory"
    memory.mkdir()
    rows = [
        {"timestamp": "2026-11-19T09:00:00", "apps": ["VS Code", "GitHub"]},
        {"timestamp": "2026-11-19T09:05:00", "apps": ["VS Code", "GitHub"]},
        {"timestamp": "2026-11-20T09:00:00", "apps": ["VS Code", "GitHub"]},
    ]
    (memory / "screen_memory_timeline.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows),
        encoding="utf-8",
    )

    result = mod.handler({"action": "analyze_patterns", "memory_dir": str(memory)})
    assert "status=done" in result
    assert "VS Code" in result

    result = mod.handler({"action": "suggest_routines", "memory_dir": str(memory)})
    assert "status=done" in result
    assert "Deseja salvar" in result or "save" in result.lower()


def test_habit_miner_save_requires_approval(tmp_path):
    import actions.habit_miner as mod

    result = mod.handler({
        "action": "save_as_routine",
        "name": "work",
        "apps": ["VS Code", "GitHub"],
        "config_path": str(tmp_path / "routines.json"),
    })
    assert "status=ask" in result
    assert not (tmp_path / "routines.json").exists()


def test_habit_miner_save_and_duplicate(tmp_path):
    import actions.habit_miner as mod

    config = tmp_path / "routines.json"
    params = {
        "action": "save_as_routine",
        "name": "modo_trabalho",
        "apps": ["VS Code", "GitHub"],
        "approved": True,
        "config_path": str(config),
    }
    first = mod.handler(params)
    second = mod.handler(params)
    assert "status=done" in first
    assert "status=done" in second
    assert "duplicate=true" in second

    data = json.loads(config.read_text(encoding="utf-8"))
    assert len(data["routines"]) == 1
