
"""Tests for mover_downloads action."""
from __future__ import annotations
from pathlib import Path
import time

from actions.productivity.mover_downloads import mover_downloads
import actions.productivity._mover_downloads_impl as impl


def test_map_destination_root():
    d = impl._map_destination("raiz")
    assert d == impl._BASE
    assert impl._map_destination("actions").name == "actions"


def test_move_newest_partial(tmp_path, monkeypatch):
    dl = tmp_path / "Downloads"
    dl.mkdir()
    old = dl / "report_old.txt"
    new = dl / "report_final.txt"
    old.write_text("old")
    time.sleep(0.02)
    new.write_text("new")
    dest = tmp_path / "project"
    dest.mkdir()
    monkeypatch.setattr(impl, "_downloads_dir", lambda: dl)
    monkeypatch.setattr(impl, "_BASE", dest)
    monkeypatch.setattr(impl, "_BACKUP", dest / "memory" / "backups")
    # re-map root to dest
    monkeypatch.setattr(impl, "_map_destination", lambda raw: dest if (raw or "root") in ("", "root", "raiz") else dest / str(raw))
    r = impl.move_file("report", "root")
    assert r["ok"] is True
    assert (dest / "report_final.txt").is_file()
    assert not new.exists()


def test_backup_on_overwrite(tmp_path, monkeypatch):
    dl = tmp_path / "Downloads"
    dl.mkdir()
    src = dl / "main.py"
    src.write_text("NEW")
    dest = tmp_path / "root"
    dest.mkdir()
    (dest / "main.py").write_text("OLD")
    monkeypatch.setattr(impl, "_downloads_dir", lambda: dl)
    monkeypatch.setattr(impl, "_BASE", dest)
    monkeypatch.setattr(impl, "_BACKUP", dest / "backups")
    monkeypatch.setattr(impl, "_map_destination", lambda raw: dest)
    r = impl.move_file("main.py", "root")
    assert r["ok"] and r.get("backup")
    assert Path(r["backup"]).is_file()
    assert (dest / "main.py").read_text() == "NEW"


def test_handler_ask_without_filename():
    r = mover_downloads({"action": "move"})
    assert "status=ask" in r or "status=failed" in r


def test_status():
    r = mover_downloads({"action": "status"})
    assert "status=done" in r
