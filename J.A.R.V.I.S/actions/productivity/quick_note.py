"""
Action: quick_note — append a timestamped note to a local file (and optional memory).

Notes live under ~/.jarvis/notes/ by default so they survive app restarts and
are easy to open in any editor. Never claims a note was saved without checking
the file exists afterwards.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

from core import outcome


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def _notes_dir() -> Path:
    d = Path.home() / ".jarvis" / "notes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_name(name: str) -> str:
    stem = re.sub(r"[^\w\-]+", "_", (name or "inbox").strip(), flags=re.UNICODE)
    stem = stem.strip("_")[:48] or "inbox"
    return stem + ".md"


def _log(msg: str, player=None) -> None:
    print(f"[Note] {msg}")
    if player:
        try:
            player.write_log(f"JARVIS: {msg}")
        except Exception:
            pass


def quick_note(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "add").strip().lower()
    text = str(params.get("text") or params.get("note") or "").strip()
    notebook = str(params.get("notebook") or params.get("name") or "inbox").strip()

    path = _notes_dir() / _safe_name(notebook)

    if action in ("list", "show", "read"):
        if not path.exists():
            return outcome.done(
                "quick_note",
                op="list",
                notebook=notebook,
                count=0,
                message=f"No notes in '{notebook}' yet.",
            )
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            return outcome.failed("quick_note", f"could not read notes file: {e}")
        # Return a short tail so the model is not drowned in history
        lines = [ln for ln in content.splitlines() if ln.strip()]
        tail = "\n".join(lines[-12:])
        return outcome.done(
            "quick_note",
            op="list",
            notebook=notebook,
            count=len(lines),
            path=str(path),
            recent=tail[:1500],
        )

    if action in ("path", "where"):
        return outcome.done(
            "quick_note",
            op="path",
            notebook=notebook,
            path=str(path),
            exists=path.exists(),
        )

    # default: add
    if not text:
        return outcome.ask(
            "quick_note",
            "What should I write down?",
        )

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"- **{stamp}** — {text}\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            if path.stat().st_size == 0:
                fh.write(f"# {notebook}\n\n")
            fh.write(entry)
    except OSError as e:
        return outcome.failed("quick_note", f"could not write note: {e}")

    # Verify it is on disk
    try:
        saved = path.exists() and text[:40] in path.read_text(encoding="utf-8")
    except OSError:
        saved = False

    if not saved:
        return outcome.unverified(
            "quick_note",
            "write returned but the note was not found on disk afterwards",
            path=str(path),
        )

    # Optional long-term memory hook (best-effort, never fails the note)
    if params.get("remember") in (True, "true", "1", "yes"):
        try:
            from memory.memory_manager import remember
            key = re.sub(r"[^\w]+", "_", text.lower())[:40] or "note"
            remember(key, text, category="notes")
        except Exception as e:
            _log(f"memory remember skipped: {e}", player)

    _log(f"Saved to {path.name}: {text[:80]}", player)
    return outcome.done(
        "quick_note",
        op="add",
        notebook=notebook,
        path=str(path),
        preview=text[:120],
    )


TOOL = {
    "name": "quick_note",
    "description": (
        "Saves a short timestamped note to a local markdown file under "
        "~/.jarvis/notes/, lists recent notes, or reports the file path. "
        "Use when the user says 'note that', 'write this down', 'remember this "
        "for later as a note', or asks to show their notes. "
        "Optional remember=true also stores it in long-term memory."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "add (default), list, or path.",
            },
            "text": {
                "type": "STRING",
                "description": "Note body when action is add.",
            },
            "notebook": {
                "type": "STRING",
                "description": "Notebook name (default 'inbox'). Becomes the file stem.",
            },
            "remember": {
                "type": "STRING",
                "description": "If 'true', also store in long-term memory notes.",
            },
        },
        "required": [],
    },
    "handler": quick_note,
}
