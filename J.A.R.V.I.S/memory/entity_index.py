"""
memory/entity_index.py — in-memory entity index for fast recall after consolidation.

Built from long_term.json + recent episodes. Not a second source of truth;
call rebuild() after compact/consolidate.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Optional

_BASE = Path(__file__).resolve().parent
_LONG = _BASE / "long_term.json"
_EPISODES = _BASE / "episodes.jsonl"

_lock = threading.RLock()
_INDEX: dict[str, set[str]] = {}  # entity_lower -> set of fact keys / episode ids
_FACTS: dict[str, str] = {}


def _tokenize_entities(text: str) -> set[str]:
    if not text:
        return set()
    # Proper-ish nouns and keywords length >= 3
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_]{3,}", text)
    out = set()
    for w in words:
        if w.lower() in {"the", "and", "for", "with", "from", "this", "that", "jarvis", "mark"}:
            continue
        out.add(w.lower())
    # multi-word Capitalized phrases
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text):
        out.add(m.group(1).lower())
    return out


def rebuild(max_episodes: int = 500) -> dict[str, Any]:
    global _INDEX, _FACTS
    idx: dict[str, set[str]] = {}
    facts: dict[str, str] = {}

    def add(entity: str, ref: str, value: str = "") -> None:
        idx.setdefault(entity, set()).add(ref)
        if value:
            facts[ref] = value[:400]

    if _LONG.is_file():
        try:
            data = json.loads(_LONG.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        for section in ("identity", "preferences", "projects", "relationships", "wishes", "notes", "monitors"):
            block = data.get(section) or {}
            if isinstance(block, dict):
                for k, v in block.items():
                    ref = "%s.%s" % (section, k)
                    blob = "%s %s" % (k, v)
                    for ent in _tokenize_entities(blob):
                        add(ent, ref, str(v))
        for i, sess in enumerate(data.get("sessions") or []):
            if isinstance(sess, dict):
                blob = json.dumps(sess, ensure_ascii=False)
            else:
                blob = str(sess)
            ref = "sessions[%d]" % i
            for ent in _tokenize_entities(blob):
                add(ent, ref, blob[:200])

    if _EPISODES.is_file():
        try:
            lines = _EPISODES.read_text(encoding="utf-8", errors="replace").splitlines()[-max_episodes:]
            for n, line in enumerate(lines):
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                blob = json.dumps(row, ensure_ascii=False)
                ref = "episode:%s" % (row.get("id") or n)
                for ent in _tokenize_entities(blob):
                    add(ent, ref, blob[:200])
        except Exception:
            pass

    with _lock:
        _INDEX = idx
        _FACTS = facts
    return {"entities": len(idx), "refs": sum(len(v) for v in idx.values())}


def lookup(query: str, limit: int = 12) -> list[dict[str, str]]:
    if not _INDEX:
        rebuild()
    q_ents = _tokenize_entities(query) or {query.strip().lower()}
    scored: dict[str, int] = {}
    with _lock:
        for ent in q_ents:
            for ref in _INDEX.get(ent, ()):
                scored[ref] = scored.get(ref, 0) + 1
            # prefix soft match
            for key, refs in _INDEX.items():
                if key.startswith(ent) or ent in key:
                    for ref in refs:
                        scored[ref] = scored.get(ref, 0) + 1
        ranked = sorted(scored.items(), key=lambda x: -x[1])[:limit]
        return [{"ref": r, "score": str(s), "value": _FACTS.get(r, "")} for r, s in ranked]


def stats() -> dict[str, int]:
    with _lock:
        return {
            "entities": len(_INDEX),
            "refs": sum(len(v) for v in _INDEX.values()),
            "facts": len(_FACTS),
        }
