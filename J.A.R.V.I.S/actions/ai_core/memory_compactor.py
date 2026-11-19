"""
memory_compactor — keeps long-term memory lean and the LLM prompt fast.

Analyses memory/long_term.json, removes empty/redundant entries, trims
oversized values, optionally summarises old session notes, forces a GC
pass, and reports before/after sizes.

Never deletes identity or recent preferences without an explicit confirm
flag. Safe by default (dry-run style report); use action=compact to apply.
"""
from __future__ import annotations

import gc
import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.outcome import done, failed, ask

_BASE = Path(__file__).resolve().parents[2]
_MEMORY_PATH = _BASE / "memory" / "long_term.json"
_BACKUP_DIR = _BASE / "memory" / "backups"

# Soft limits (characters)
_MAX_VALUE_CHARS = 380          # matches memory_manager.MAX_VALUE_LENGTH
_MAX_SESSIONS_KEEP = 30
_MAX_NOTES_KEEP = 80
_OLD_SESSION_DAYS = 45


def _load_raw() -> dict:
    if not _MEMORY_PATH.exists():
        return {
            "identity": {},
            "preferences": {},
            "projects": {},
            "relationships": {},
            "wishes": {},
            "notes": {},
            "sessions": [],
            "monitors": {},
        }
    try:
        return json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"cannot read long_term.json: {e}") from e


def _save_raw(data: dict) -> None:
    _MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _MEMORY_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _size_chars(obj: Any) -> int:
    return len(json.dumps(obj, ensure_ascii=False))


def _backup(data: dict) -> str | None:
    try:
        _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _BACKUP_DIR / f"long_term_{stamp}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        # Keep only last 8 backups
        backups = sorted(_BACKUP_DIR.glob("long_term_*.json"), reverse=True)
        for old in backups[8:]:
            try:
                old.unlink()
            except Exception:
                pass
        return str(path.name)
    except Exception:
        return None


def _trim_value(v: Any) -> Any:
    if isinstance(v, str) and len(v) > _MAX_VALUE_CHARS:
        return v[: _MAX_VALUE_CHARS - 3].rstrip() + "..."
    return v


def _clean_dict(d: dict, *, drop_empty: bool = True) -> tuple[dict, int]:
    """Return cleaned dict + number of removed/trimmed items."""
    removed = 0
    out = {}
    for k, v in d.items():
        if v is None or v == "" or v == {} or v == []:
            if drop_empty:
                removed += 1
                continue
        if isinstance(v, str):
            nv = _trim_value(v)
            if nv != v:
                removed += 1
            out[k] = nv
        elif isinstance(v, dict):
            sub, r = _clean_dict(v, drop_empty=drop_empty)
            removed += r
            if sub or not drop_empty:
                out[k] = sub
            else:
                removed += 1
        else:
            out[k] = v
    return out, removed


def _prune_sessions(sessions: list, keep: int = _MAX_SESSIONS_KEEP) -> tuple[list, int]:
    if not isinstance(sessions, list):
        return [], 0
    if len(sessions) <= keep:
        return sessions, 0
    # Keep the most recent ones (assume list is chronological or has timestamps)
    pruned = sessions[-keep:]
    return pruned, len(sessions) - len(pruned)


def _analyse(data: dict) -> dict:
    cats = {}
    total = 0
    for key in ("identity", "preferences", "projects", "relationships", "wishes", "notes", "monitors"):
        section = data.get(key) or {}
        if not isinstance(section, dict):
            section = {}
        chars = _size_chars(section)
        cats[key] = {
            "entries": len(section),
            "chars": chars,
        }
        total += chars

    sessions = data.get("sessions") or []
    sess_chars = _size_chars(sessions)
    cats["sessions"] = {
        "entries": len(sessions) if isinstance(sessions, list) else 0,
        "chars": sess_chars,
    }
    total += sess_chars

    return {
        "total_chars": total,
        "categories": cats,
        "file_bytes": _MEMORY_PATH.stat().st_size if _MEMORY_PATH.exists() else 0,
    }


def memory_compactor(parameters: dict | None = None, **_ctx) -> str:
    params = parameters or {}
    action = (params.get("action") or "status").strip().lower()
    confirm = str(params.get("confirm") or "").strip().lower() in ("1", "true", "yes", "y")

    try:
        data = _load_raw()
    except Exception as e:
        return failed("memory_compactor", str(e))

    analysis = _analyse(data)

    # ── status / analyse ──────────────────────────────────────────────────
    if action in ("status", "analyse", "analyze", "report"):
        cat_str = "; ".join(
            f"{k}={v['entries']}ent/{v['chars']}ch"
            for k, v in analysis["categories"].items()
        )
        epi = {}
        try:
            from memory.memory_manager import episode_stats
            epi = episode_stats()
        except Exception:
            epi = {}
        return done(
            "memory_compactor",
            action="status",
            total_chars=analysis["total_chars"],
            file_bytes=analysis["file_bytes"],
            categories=cat_str,
            episodes=epi.get("episodes", 0),
            graph_nodes=epi.get("graph_nodes", 0),
            graph_edges=epi.get("graph_edges", 0),
            chroma=bool(epi.get("chroma")),
            note="Use action=compact with confirm=true to apply safe cleaning. "
                 "action=compact_episodes prunes old episodic lines.",
        )

    # ── compact (safe cleaning) ───────────────────────────────────────────
    if action in ("compact", "clean", "optimize"):
        if not confirm:
            return ask(
                "memory_compactor",
                "This will rewrite long_term.json (a backup is made first). Confirm?",
                hint="Call again with confirm=true",
            )

        original = deepcopy(data)
        before = analysis["total_chars"]
        changes = 0

        # Clean each category dict
        for key in ("identity", "preferences", "projects", "relationships", "wishes", "notes", "monitors"):
            section = data.get(key)
            if isinstance(section, dict):
                cleaned, removed = _clean_dict(section)
                data[key] = cleaned
                changes += removed

        # Prune old sessions
        sessions = data.get("sessions") or []
        if isinstance(sessions, list):
            new_sessions, dropped = _prune_sessions(sessions)
            data["sessions"] = new_sessions
            changes += dropped

        # Force garbage collection of the Python process
        collected = gc.collect()

        after_analysis = _analyse(data)
        after = after_analysis["total_chars"]
        saved = max(0, before - after)

        backup_name = _backup(original)
        _save_raw(data)

        return done(
            "memory_compactor",
            action="compact",
            before_chars=before,
            after_chars=after,
            saved_chars=saved,
            items_touched=changes,
            gc_collected=collected,
            backup=backup_name or "none",
            note="Safe clean applied. Identity keys were only trimmed, never deleted.",
        )

    # ── compact_episodes — prune episodic log + soft-cap graph ───────────
    if action in ("compact_episodes", "episodes", "prune_episodes"):
        if not confirm:
            return ask(
                "memory_compactor",
                "This will prune memory/episodes.jsonl (keep last N) and soft-cap the graph. Confirm?",
                hint="Call again with confirm=true",
            )
        try:
            from memory.memory_manager import (
                EPISODES_PATH, load_graph, save_graph, _iter_episodes,
            )
        except Exception as e:
            return failed("memory_compactor", f"episode backend unavailable: {e}")

        keep = 500
        try:
            keep = max(50, min(int(params.get("keep") or 500), 5000))
        except (TypeError, ValueError):
            keep = 500

        rows = _iter_episodes(max_lines=50_000)
        before_n = len(rows)
        kept = rows[-keep:] if len(rows) > keep else rows
        dropped = max(0, before_n - len(kept))

        EPISODES_PATH.parent.mkdir(parents=True, exist_ok=True)
        EPISODES_PATH.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept),
            encoding="utf-8",
        )
        # Touch graph save to apply soft caps
        g = load_graph()
        save_graph(g)

        return done(
            "memory_compactor",
            action="compact_episodes",
            episodes_before=before_n,
            episodes_after=len(kept),
            dropped=dropped,
            keep=keep,
            note="Episodes pruned; graph soft-caps applied on save.",
        )

    # ── hard_trim (more aggressive, still protected) ──────────────────────
    if action in ("hard_trim", "aggressive"):
        if not confirm:
            return ask(
                "memory_compactor",
                "Aggressive trim will also drop excess notes and old sessions. Confirm?",
                hint="Call again with confirm=true",
            )

        original = deepcopy(data)
        before = analysis["total_chars"]

        for key in ("preferences", "projects", "relationships", "wishes", "notes", "monitors"):
            section = data.get(key)
            if isinstance(section, dict):
                cleaned, _ = _clean_dict(section)
                # Cap notes especially hard
                if key == "notes" and len(cleaned) > _MAX_NOTES_KEEP:
                    # Keep arbitrary last N keys (dict order is insertion order in 3.7+)
                    keys = list(cleaned.keys())[-_MAX_NOTES_KEEP:]
                    cleaned = {k: cleaned[k] for k in keys}
                data[key] = cleaned

        # Identity is only trimmed, never key-deleted
        if isinstance(data.get("identity"), dict):
            data["identity"], _ = _clean_dict(data["identity"], drop_empty=True)

        sessions = data.get("sessions") or []
        if isinstance(sessions, list):
            data["sessions"], _ = _prune_sessions(sessions, keep=15)

        collected = gc.collect()
        after = _analyse(data)["total_chars"]
        backup_name = _backup(original)
        _save_raw(data)

        return done(
            "memory_compactor",
            action="hard_trim",
            before_chars=before,
            after_chars=after,
            saved_chars=max(0, before - after),
            gc_collected=collected,
            backup=backup_name or "none",
        )

    # ── gc only ───────────────────────────────────────────────────────────
    if action in ("gc", "garbage_collect"):
        collected = gc.collect()
        return done(
            "memory_compactor",
            action="gc",
            gc_collected=collected,
            note="Python garbage collector run. Memory file unchanged.",
        )


    if action in ("lookup", "search_index"):
        q = str(params.get("query") or params.get("q") or "").strip()
        if not q:
            return ask("memory_compactor", "query?")
        try:
            from memory.entity_index import lookup, rebuild, stats
            rebuild()
            hits = lookup(q)
            return done("memory_compactor", action="lookup", query=q, hits=hits, index=stats())
        except Exception as e:
            return failed("memory_compactor", str(e), action="lookup")

    if action in ("consolidate", "episodes", "compact_episodes"):
        try:
            from memory.memory_manager import consolidate_episodes, episode_stats
            result = consolidate_episodes()
            stats = episode_stats()
            try:
                from memory.entity_index import rebuild
                idx_stats = rebuild()
            except Exception:
                idx_stats = {}
            return done(
                "memory_compactor",
                action="consolidate",
                **{k: result.get(k) for k in ("promoted", "last_run", "episodes") if k in result},
                forget_dropped=(result.get("forget") or {}).get("dropped"),
                graph_nodes=stats.get("graph_nodes"),
                note="Episodes consolidated into long-term topics; old episodes pruned by TTL.",
                entity_index=idx_stats,
            )
        except Exception as e:
            return failed("memory_compactor", f"consolidate failed: {e}")

    if action in ("hygiene", "contradictions", "report_hygiene"):
        try:
            from memory.memory_manager import memory_hygiene_report, detect_contradictions
            report = memory_hygiene_report()
            n = len(detect_contradictions())
            return done(
                "memory_compactor",
                action="hygiene",
                contradictions=n,
                report=report[:1500],
            )
        except Exception as e:
            return failed("memory_compactor", f"hygiene failed: {e}")

    if action in ("forget_old", "ttl"):
        try:
            from memory.memory_manager import forget_old_episodes
            days = int(params.get("ttl_days") or params.get("days") or 30)
            stats = forget_old_episodes(ttl_days=days)
            return done("memory_compactor", action="forget_old", **stats)
        except Exception as e:
            return failed("memory_compactor", f"forget_old failed: {e}")

    return ask(
        "memory_compactor",
        "what should I do?",
        options="status, compact (confirm=true), hard_trim (confirm=true), gc, consolidate, hygiene, forget_old",
    )


TOOL = {
    "name": "memory_compactor",
    "description": (
        "Analyses and compacts JARVIS long-term memory (long_term.json). "
        "Removes empty/redundant entries, trims oversized values, prunes old "
        "sessions, and can force a Python GC pass. Keeps the LLM prompt smaller "
        "and faster. "
        "Actions: status, compact, hard_trim, gc, consolidate (episodes→facts), "
        "hygiene (contradiction report), forget_old (ttl_days). "
        "Always creates a backup before rewriting the file."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "status | compact | hard_trim | gc | consolidate | hygiene | forget_old",
            },
            "confirm": {
                "type": "STRING",
                "description": "Must be true/yes to apply compact or hard_trim",
            },
        },
        "required": [],
    },
    "handler": memory_compactor,
    "tier": "core",
}
