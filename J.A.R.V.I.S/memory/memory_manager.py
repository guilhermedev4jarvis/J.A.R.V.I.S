import json
import re
from datetime import datetime
from threading import Lock
from pathlib import Path
import sys


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR         = get_base_dir()
MEMORY_PATH      = BASE_DIR / "memory" / "long_term.json"
_lock            = Lock()
MAX_VALUE_LENGTH = 380

# ── Why there are two very different numbers here ────────────────────────────
#
# There used to be one: MEMORY_MAX_CHARS = 2200, applied to the whole store. It
# was a *storage* limit, and it existed only because the entire memory was
# pasted into the system prompt on every connect — so growing the memory grew
# every single request. When it filled, _trim_to_limit() deleted the oldest
# entries and printed one line to a console nobody reads. A memory described as
# "deeply remembers projects, preferences and personal context" was in practice
# two pages long, and quietly forgot your sister's name after a few weeks.
#
# Storage and prompt budget are now separate concerns:
#
#   MEMORY_MAX_CHARS  — a runaway guard, not a feature limit. Nothing normal
#                       reaches it; a bug writing in a loop does.
#   PROMPT_CORE_CHARS — what actually rides in the system prompt every session.
#                       Smaller than the old whole-memory dump, so sessions
#                       start *faster* than before, not slower.
#
# Everything above the core stays on disk and is fetched on demand by the
# recall_memory tool — see search_memory() and format_memory_for_prompt().
MEMORY_MAX_CHARS  = 200_000
PROMPT_CORE_CHARS = 900
PROMPT_INDEX_CHARS = 420
# Most entries any one category may contribute to the core block, so a person
# with forty stored preferences still gets their sister into the prompt.
PROMPT_MAX_PER_CATEGORY = 6

def _empty_memory() -> dict:
    return {
        "identity":      {},
        "preferences":   {},
        "projects":      {},
        "relationships": {},
        "wishes":        {},
        "notes":         {},
    }

def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        return _empty_memory()
    with _lock:
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _empty_memory()
                for key in base:
                    if key not in data:
                        data[key] = {}
                return data
            return _empty_memory()
        except Exception as e:
            print(f"[Memory] ⚠️ Load error: {e}")
            return _empty_memory()

def _all_entries(memory: dict) -> list[tuple]:
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries


# Set by main.py so a trim can reach the activity log. Deleting something a
# person told you and mentioning it only on stdout is how a memory loses trust.
_trim_notifier = None


def set_trim_notifier(fn) -> None:
    """Register a callable(str) that surfaces trims to the user."""
    global _trim_notifier
    _trim_notifier = fn


def _trim_to_limit(memory: dict) -> dict:
    if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
        return memory
    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))
    dropped = []
    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        dropped.append(f"{cat}/{key}")
        print(f"[Memory] 🗑️  Trimmed {cat}/{key}")
    if dropped and _trim_notifier:
        try:
            _trim_notifier(
                f"SYS: Memory full — forgot {len(dropped)} oldest entries "
                f"({', '.join(dropped[:3])}{'…' if len(dropped) > 3 else ''})"
            )
        except Exception:
            pass
    return memory

def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    memory = _trim_to_limit(memory)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            new_val  = _truncate_value(str(value["value"] if isinstance(value, dict) else value))
            entry    = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
            existing = target.get(key, {})
            if not isinstance(existing, dict) or existing.get("value") != new_val:
                target[key] = entry
                changed = True
    return changed


def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
        print(f"[Memory] 💾 Saved: {list(memory_update.keys())}")
    return memory

def _entry_value(entry) -> str:
    """Accept both the {'value': ..., 'updated': ...} shape and a bare string,
    because early versions of the store wrote plain strings."""
    if isinstance(entry, dict):
        return str(entry.get("value", "") or "").strip()
    return str(entry or "").strip()


def _pretty(key: str) -> str:
    return key.replace("_", " ").strip()


# Identity is always in the prompt; these categories compete for the remaining
# budget by recency.
_CATEGORY_LABELS = {
    "preferences":   "Preferences",
    "projects":      "Active projects / goals",
    "relationships": "People in their life",
    "wishes":        "Wishes / plans",
    "notes":         "Notes",
}

_IDENTITY_FIELDS = ["name", "age", "birthday", "city", "job",
                    "language", "school", "nationality"]


def format_memory_for_prompt(memory: dict | None) -> str:
    """Build the memory block that goes into the system prompt.

    This used to dump everything. It now sends three things:

      1. IDENTITY  - always, in full. It is small, and it is wrong for the
         assistant to have to look up your name.
      2. RECENT    - the most recently updated entries from every other
         category, up to PROMPT_CORE_CHARS. Recency is the cheapest useful
         relevance signal available without embeddings.
      3. AN INDEX  - the *keys* of everything else, values omitted.

    Point 3 is what makes recall work at all. A model cannot decide to look
    something up if it does not know the thing exists: with only points 1 and 2,
    "who is Ayse?" would get "I don't know" while ayse_sister sat on disk
    unread. The index costs a few hundred characters and turns recall from a
    gamble into a lookup.

    Net effect on latency: this block is SMALLER than the old full dump, so
    every session connects with fewer tokens. Occasionally the model spends one
    extra round trip on recall_memory - covered by the acknowledgment it
    already speaks before any slow step."""
    if not memory:
        return ""

    core_lines: list[str] = []

    # 1. Identity - always, in full
    identity = memory.get("identity", {}) or {}
    for field in _IDENTITY_FIELDS:
        val = _entry_value(identity.get(field))
        if not val:
            continue
        if field == "language":
            # Labelled as an observation, not a setting. A bare "Language:
            # English" line written months ago reads like a standing order and
            # was one of the reasons a Turkish question came back in English.
            core_lines.append(
                f"Has spoken to you in: {val} (an observation about the past — "
                f"always answer in the language of their CURRENT message)")
        else:
            core_lines.append(f"{field.title()}: {val}")
    for key, entry in identity.items():
        if key in _IDENTITY_FIELDS:
            continue
        val = _entry_value(entry)
        if val:
            core_lines.append(f"{_pretty(key).title()}: {val}")

    # 2. Everything else, most recently updated first
    rest: list[tuple[str, str, str, str]] = []   # (updated, cat, key, value)
    for cat in _CATEGORY_LABELS:
        for key, entry in (memory.get(cat, {}) or {}).items():
            val = _entry_value(entry)
            if not val:
                continue
            updated = (entry.get("updated", "") if isinstance(entry, dict) else "") or "0000-00-00"
            rest.append((updated, cat, key, val))
    rest.sort(key=lambda t: t[0], reverse=True)

    used    = sum(len(l) + 1 for l in core_lines)
    shown: dict[str, list[str]] = {}
    overflow: dict[str, list[str]] = {}

    # Recency decides order, but no single category may take the whole budget.
    # Without the cap, someone with forty stored preferences gets a prompt that
    # is forty preferences and not one person's name — the categories that
    # matter most in conversation are also the ones that change least often, so
    # pure recency systematically buries them.
    per_cat_used: dict[str, int] = {}
    for _updated, cat, key, val in rest:
        line = f"  - {_pretty(key).title()}: {val}"
        if (per_cat_used.get(cat, 0) < PROMPT_MAX_PER_CATEGORY
                and used + len(line) + 1 <= PROMPT_CORE_CHARS):
            shown.setdefault(cat, []).append(line)
            per_cat_used[cat] = per_cat_used.get(cat, 0) + 1
            used += len(line) + 1
        else:
            overflow.setdefault(cat, []).append(_pretty(key))

    # The index is a table of contents, so it is interleaved across categories
    # rather than continuing in recency order. Sorted by recency it would list
    # twenty-four preferences before the first relationship, and the one entry
    # the index exists for — the old fact the model has no other way to know
    # about — would fall off the end.
    indexed: list[str] = []
    if overflow:
        cats  = [c for c in _CATEGORY_LABELS if overflow.get(c)]
        cursor = {c: 0 for c in cats}
        while cats:
            for cat in list(cats):
                i = cursor[cat]
                if i >= len(overflow[cat]):
                    cats.remove(cat)
                    continue
                indexed.append(overflow[cat][i])
                cursor[cat] = i + 1

    for cat, label in _CATEGORY_LABELS.items():
        if shown.get(cat):
            core_lines.append("")
            core_lines.append(f"{label}:")
            core_lines.extend(shown[cat])

    if not core_lines and not indexed:
        return ""

    out = [
        "[WHAT YOU KNOW ABOUT THIS PERSON — use naturally, never recite like a list]",
        *core_lines,
    ]

    # 3. The index of what is on disk but not in this prompt
    if indexed:
        budget, names = PROMPT_INDEX_CHARS, []
        for n in indexed:
            if budget - len(n) - 2 < 0:
                break
            names.append(n)
            budget -= len(n) + 2
        if names:
            out.append("")
            out.append(
                "[ALSO REMEMBERED — values not shown here. Call recall_memory "
                "with a keyword to read any of these before saying you do not know]"
            )
            out.append(", ".join(names)
                       + (f" (+{len(indexed) - len(names)} more)"
                          if len(indexed) > len(names) else ""))

    return "\n".join(out) + "\n"


# ── Recall ────────────────────────────────────────────────────────────────────

def _score(query_words: list[str], cat: str, key: str, value: str) -> int:
    """Cheap lexical relevance. No embeddings, no network, no model call - this
    runs in well under a millisecond, which is the entire point: recall must
    cost one model round trip, never two."""
    hay_key = _pretty(key).lower()
    hay_val = value.lower()
    score   = 0
    for w in query_words:
        if not w:
            continue
        if w == hay_key:
            score += 10
        elif w in hay_key:
            score += 6
        if w in hay_val:
            score += 3
        if w in cat:
            score += 1
    return score


def search_memory(query: str, limit: int = 8) -> str:
    """Find stored facts matching `query`. Backs the recall_memory tool.

    An empty query is treated as "show me everything you know", capped - the
    model asks that when the user says "what do you remember about me?"."""
    memory = load_memory()
    words  = [w for w in re.split(r"[^\w]+", (query or "").lower()) if len(w) > 1]

    rows: list[tuple[int, str, str, str]] = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue                     # skip 'sessions', which is a list
        for key, entry in items.items():
            val = _entry_value(entry)
            if not val:
                continue
            s = _score(words, cat, key, val) if words else 1
            if s > 0:
                rows.append((s, cat, key, val))

    if not rows:
        return (f"Nothing stored about '{query}'." if query
                else "I have not stored anything about this person yet.")

    rows.sort(key=lambda r: (-r[0], r[2]))
    lines = [f"{cat}/{_pretty(key)}: {val}" for _s, cat, key, val in rows[:max(1, limit)]]
    head  = (f"Stored facts matching '{query}':" if query
             else "Everything currently stored:")
    more  = (f"\n(+{len(rows) - len(lines)} more — search with a narrower keyword)"
             if len(rows) > len(lines) else "")
    return head + "\n" + "\n".join(lines) + more


def all_entries_for_ui() -> list[dict]:
    """Flat list for the memory panel: what JARVIS knows, and when it learned it.
    Sorted newest first so the panel opens on what changed most recently."""
    memory = load_memory()
    rows = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            val = _entry_value(entry)
            if not val:
                continue
            rows.append({
                "category": cat,
                "key":      key,
                "value":    val,
                "updated":  (entry.get("updated", "") if isinstance(entry, dict) else ""),
            })
    rows.sort(key=lambda r: (r["updated"] or "0000-00-00"), reverse=True)
    return rows

def remember(key: str, value: str, category: str = "notes") -> str:
    valid = {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
    if category not in valid:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    memory = load_memory()
    cat    = memory.get(category, {})
    if key in cat:
        del cat[key]
        memory[category] = cat
        save_memory(memory)
        return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"


forget_memory = forget


# ── Session memory ─────────────────────────────────────────────────────────────

_SESSION_MAX = 3   # safety cap — in practice 0-1 entries after pop


def save_session_summary(summary: str, language: str = "") -> None:
    """Append a 1-2 sentence session summary to long_term.json['sessions']."""
    summary = (summary or "").strip()
    if not summary:
        return
    memory   = load_memory()
    sessions = memory.get("sessions", [])
    if not isinstance(sessions, list):
        sessions = []
    entry: dict = {
        "date":    datetime.now().strftime("%Y-%m-%d"),
        "summary": summary[:280],
    }
    if language:
        entry["language"] = language
    sessions.append(entry)
    memory["sessions"] = sessions[-_SESSION_MAX:]
    with _lock:
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    print(f"[Memory] 📝 Session saved ({entry['date']}): {summary[:60]}…")


def pop_last_session() -> dict | None:
    """
    Return AND remove the most recent session entry.
    Calling this consumes the entry so it is never repeated in future briefings.
    """
    with _lock:
        if not MEMORY_PATH.exists():
            return None
        try:
            memory   = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            sessions = memory.get("sessions", [])
            if not isinstance(sessions, list) or not sessions:
                return None
            entry = sessions.pop()          # remove the last entry
            memory["sessions"] = sessions
            MEMORY_PATH.write_text(
                json.dumps(memory, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return entry
        except Exception as e:
            print(f"[Memory] ⚠️ pop_last_session error: {e}")
            return None


# ── Episodic memory + lightweight knowledge graph ─────────────────────────────
#
# long_term.json stays the canonical fact store (identity, preferences, …).
# Episodes and the graph live beside it so the prompt budget is unchanged:
#   memory/episodes.jsonl   — one JSON object per line (append-only log)
#   memory/graph.json       — nodes + edges (people, projects, prefs links)
#
# Optional ChromaDB: if installed, episodes are also embedded for semantic
# search. Without it, search falls back to keyword scoring (same spirit as
# search_memory).

EPISODES_PATH = BASE_DIR / "memory" / "episodes.jsonl"
GRAPH_PATH    = BASE_DIR / "memory" / "graph.json"
_EPISODE_MAX_CHARS = 600
_EPISODE_SEARCH_LIMIT = 8
_GRAPH_MAX_NODES = 400
_GRAPH_MAX_EDGES = 800


def _empty_graph() -> dict:
    return {"nodes": {}, "edges": []}


def load_graph() -> dict:
    if not GRAPH_PATH.exists():
        return _empty_graph()
    with _lock:
        try:
            data = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return _empty_graph()
            data.setdefault("nodes", {})
            data.setdefault("edges", [])
            if not isinstance(data["nodes"], dict):
                data["nodes"] = {}
            if not isinstance(data["edges"], list):
                data["edges"] = []
            return data
        except Exception as e:
            print(f"[Memory] ⚠️ graph load error: {e}")
            return _empty_graph()


def save_graph(graph: dict) -> None:
    if not isinstance(graph, dict):
        return
    nodes = graph.get("nodes") or {}
    edges = graph.get("edges") or []
    # Soft caps so the file cannot grow without bound.
    if len(nodes) > _GRAPH_MAX_NODES:
        # Drop oldest by updated stamp
        items = sorted(
            ((k, v) for k, v in nodes.items() if isinstance(v, dict)),
            key=lambda kv: kv[1].get("updated", ""),
        )
        for k, _ in items[: max(0, len(nodes) - _GRAPH_MAX_NODES)]:
            nodes.pop(k, None)
        graph["nodes"] = nodes
    if len(edges) > _GRAPH_MAX_EDGES:
        graph["edges"] = edges[-_GRAPH_MAX_EDGES:]
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        GRAPH_PATH.write_text(
            json.dumps(graph, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def upsert_node(node_id: str, label: str = "", kind: str = "entity",
                meta: dict | None = None) -> None:
    """Create or refresh a graph node. kind: person|project|preference|entity|place."""
    node_id = re.sub(r"\s+", "_", (node_id or "").strip().lower())[:80]
    if not node_id:
        return
    graph = load_graph()
    nodes = graph.setdefault("nodes", {})
    prev = nodes.get(node_id) if isinstance(nodes.get(node_id), dict) else {}
    nodes[node_id] = {
        "id": node_id,
        "label": (label or prev.get("label") or node_id)[:120],
        "kind": (kind or prev.get("kind") or "entity")[:40],
        "meta": {**(prev.get("meta") or {}), **(meta or {})},
        "updated": datetime.now().strftime("%Y-%m-%d"),
    }
    graph["nodes"] = nodes
    save_graph(graph)


def link(src: str, rel: str, dst: str, weight: float = 1.0) -> None:
    """Add (or reinforce) an edge src -rel→ dst."""
    src = re.sub(r"\s+", "_", (src or "").strip().lower())[:80]
    dst = re.sub(r"\s+", "_", (dst or "").strip().lower())[:80]
    rel = re.sub(r"\s+", "_", (rel or "related_to").strip().lower())[:40]
    if not src or not dst or src == dst:
        return
    graph = load_graph()
    edges = graph.setdefault("edges", [])
    for e in edges:
        if (isinstance(e, dict) and e.get("src") == src
                and e.get("rel") == rel and e.get("dst") == dst):
            e["weight"] = float(e.get("weight") or 1) + float(weight)
            e["updated"] = datetime.now().strftime("%Y-%m-%d")
            save_graph(graph)
            return
    edges.append({
        "src": src, "rel": rel, "dst": dst,
        "weight": float(weight),
        "updated": datetime.now().strftime("%Y-%m-%d"),
    })
    graph["edges"] = edges
    # Ensure endpoints exist
    nodes = graph.setdefault("nodes", {})
    for nid in (src, dst):
        if nid not in nodes:
            nodes[nid] = {
                "id": nid, "label": nid, "kind": "entity", "meta": {},
                "updated": datetime.now().strftime("%Y-%m-%d"),
            }
    save_graph(graph)


def related(entity: str, limit: int = 12) -> str:
    """Neighbours of an entity in the knowledge graph (for recall tools)."""
    entity = re.sub(r"\s+", "_", (entity or "").strip().lower())[:80]
    if not entity:
        return "No entity given."
    graph = load_graph()
    nodes = graph.get("nodes") or {}
    edges = graph.get("edges") or []
    hits = []
    for e in edges:
        if not isinstance(e, dict):
            continue
        if e.get("src") == entity:
            other = e.get("dst")
            direction = f"-[{e.get('rel')}]->"
        elif e.get("dst") == entity:
            other = e.get("src")
            direction = f"<-[{e.get('rel')}]-"
        else:
            continue
        label = ""
        n = nodes.get(other) if isinstance(nodes.get(other), dict) else None
        if n:
            label = n.get("label") or other
            kind = n.get("kind") or ""
            hits.append((float(e.get("weight") or 1), f"{direction} {label} ({kind})"))
        else:
            hits.append((float(e.get("weight") or 1), f"{direction} {other}"))
    if not hits:
        # Fuzzy: substring match on node ids/labels
        soft = []
        q = entity.replace("_", " ")
        for nid, n in nodes.items():
            if not isinstance(n, dict):
                continue
            hay = f"{nid} {n.get('label', '')}".lower()
            if q in hay or entity in nid:
                soft.append(f"{n.get('kind', 'entity')}: {n.get('label') or nid}")
        if soft:
            return "Graph nodes matching query:\n" + "\n".join(soft[:limit])
        return f"Nothing linked to '{entity}' in the knowledge graph yet."
    hits.sort(key=lambda t: -t[0])
    lines = [t[1] for t in hits[:limit]]
    return f"Related to '{entity}':\n" + "\n".join(lines)


def add_episode(text: str, role: str = "user",
                entities: list[str] | None = None,
                summary: str = "") -> str:
    """Append one episodic memory line and optionally touch the graph."""
    text = (text or "").strip()
    if not text:
        return "Empty episode ignored."
    text = text[:_EPISODE_MAX_CHARS]
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "role": (role or "user")[:20],
        "text": text,
        "summary": (summary or "")[:240],
        "entities": [re.sub(r"\s+", "_", e.strip().lower())[:60]
                     for e in (entities or []) if e and str(e).strip()][:12],
    }
    EPISODES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with EPISODES_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Graph: ensure entity nodes exist and weak co-mention links
    ents = entry["entities"]
    for e in ents:
        upsert_node(e, label=e.replace("_", " "), kind="entity")
    for i, a in enumerate(ents):
        for b in ents[i + 1:]:
            link(a, "mentioned_with", b, weight=0.5)

    # Optional Chroma embedding (never required)
    try:
        _chroma_add(entry)
    except Exception as e:
        print(f"[Memory] chroma skip: {e}")

    return f"Episode stored ({entry['ts']})."


def _iter_episodes(max_lines: int = 2000) -> list[dict]:
    if not EPISODES_PATH.exists():
        return []
    rows: list[dict] = []
    with _lock:
        try:
            lines = EPISODES_PATH.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
    for line in lines[-max_lines:]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and obj.get("text"):
                rows.append(obj)
        except Exception:
            continue
    return rows


def _score_episode(words: list[str], ep: dict) -> int:
    hay = f"{ep.get('text', '')} {ep.get('summary', '')} {' '.join(ep.get('entities') or [])}".lower()
    score = 0
    for w in words:
        if w in hay:
            score += 3 if len(w) > 3 else 1
    return score


def search_episodes(query: str, limit: int = _EPISODE_SEARCH_LIMIT) -> str:
    """Keyword (+ optional vector) search over episodic memory."""
    query = (query or "").strip()
    limit = max(1, min(int(limit or _EPISODE_SEARCH_LIMIT), 20))

    # Try Chroma first
    try:
        chroma_hits = _chroma_search(query, limit=limit)
        if chroma_hits:
            lines = [f"[{h.get('ts', '')}] {h.get('text', '')[:200]}" for h in chroma_hits]
            return "Episodes (semantic):\n" + "\n".join(lines)
    except Exception:
        pass

    words = [w for w in re.split(r"[^\w]+", query.lower()) if len(w) > 1]
    rows = _iter_episodes()
    if not rows:
        return "No episodes stored yet."
    if not words:
        recent = rows[-limit:]
        lines = [f"[{r.get('ts', '')}] {r.get('text', '')[:200]}" for r in reversed(recent)]
        return "Recent episodes:\n" + "\n".join(lines)

    scored = []
    for ep in rows:
        s = _score_episode(words, ep)
        if s > 0:
            scored.append((s, ep))
    if not scored:
        return f"No episodes matching '{query}'."
    scored.sort(key=lambda t: (-t[0], t[1].get("ts", "")))
    lines = [f"[{ep.get('ts', '')}] {ep.get('text', '')[:200]}" for _s, ep in scored[:limit]]
    return f"Episodes matching '{query}':\n" + "\n".join(lines)


def search_memory_rich(query: str, limit: int = 8) -> str:
    """Facts + episodes + graph neighbours in one recall blob."""
    parts = [search_memory(query, limit=limit)]
    ep = search_episodes(query, limit=min(5, limit))
    if ep and not ep.startswith("No episodes"):
        parts.append(ep)
    # If query looks like an entity, add graph
    token = re.sub(r"\s+", "_", query.strip().lower())[:80]
    if token:
        rel = related(token, limit=6)
        if not rel.startswith("Nothing linked"):
            parts.append(rel)
    return "\n\n".join(parts)


# ── Optional ChromaDB backend ────────────────────────────────────────────────

def _chroma_collection():
    import importlib.util
    if importlib.util.find_spec("chromadb") is None:
        return None
    import chromadb
    from chromadb.config import Settings
    path = str(BASE_DIR / "memory" / "chroma")
    client = chromadb.PersistentClient(path=path, settings=Settings(anonymized_telemetry=False))
    return client.get_or_create_collection(name="jarvis_episodes")


def _chroma_add(entry: dict) -> None:
    col = _chroma_collection()
    if col is None:
        return
    eid = entry.get("ts") or datetime.now().isoformat()
    eid = re.sub(r"[^0-9A-Za-z_\-]", "_", eid) + "_" + str(abs(hash(entry.get("text", ""))) % 10_000)
    col.upsert(
        ids=[eid],
        documents=[entry.get("text") or ""],
        metadatas=[{
            "ts": entry.get("ts") or "",
            "role": entry.get("role") or "",
            "summary": (entry.get("summary") or "")[:200],
        }],
    )


def _chroma_search(query: str, limit: int = 5) -> list[dict]:
    if not (query or "").strip():
        return []
    col = _chroma_collection()
    if col is None:
        return []
    res = col.query(query_texts=[query], n_results=limit)
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    out = []
    for doc, meta in zip(docs, metas):
        out.append({
            "text": doc,
            "ts": (meta or {}).get("ts", ""),
            "role": (meta or {}).get("role", ""),
        })
    return out


def episode_stats() -> dict:
    rows = _iter_episodes()
    graph = load_graph()
    return {
        "episodes": len(rows),
        "graph_nodes": len(graph.get("nodes") or {}),
        "graph_edges": len(graph.get("edges") or []),
        "episodes_path": str(EPISODES_PATH),
        "graph_path": str(GRAPH_PATH),
        "chroma": _chroma_collection() is not None,
    }


# ── Memory quality: consolidation, forget policy, hygiene ────────────────────

_CONSOLIDATE_STATE = BASE_DIR / "memory" / "consolidate_state.json"
_DEFAULT_EPISODE_TTL_DAYS = 30
_MIN_EPISODES_TO_COMPACT = 40


def _load_consolidate_state() -> dict:
    try:
        return json.loads(_CONSOLIDATE_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"last_run": None, "facts_promoted": 0, "episodes_dropped": 0}


def _save_consolidate_state(data: dict) -> None:
    try:
        _CONSOLIDATE_STATE.parent.mkdir(parents=True, exist_ok=True)
        _CONSOLIDATE_STATE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except Exception as e:
        print(f"[memory] consolidate state save failed: {e}")


def _parse_ts(ts: str):
    from datetime import datetime
    if not ts:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(ts[:26], fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(ts.replace("Z", ""))
    except Exception:
        return None


def forget_old_episodes(ttl_days: int = _DEFAULT_EPISODE_TTL_DAYS) -> dict:
    """Drop episodes older than *ttl_days*. Keeps graph intact.

    Returns stats. Safe to call repeatedly.
    """
    from datetime import datetime, timedelta

    if not EPISODES_PATH.is_file():
        return {"kept": 0, "dropped": 0}
    cutoff = datetime.now() - timedelta(days=max(1, int(ttl_days)))
    kept_lines: list[str] = []
    dropped = 0
    try:
        for line in EPISODES_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                ep = json.loads(line)
            except Exception:
                kept_lines.append(line)
                continue
            ts = _parse_ts(str(ep.get("ts") or ""))
            if ts is not None and ts < cutoff:
                dropped += 1
                continue
            kept_lines.append(line)
        if dropped:
            EPISODES_PATH.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""), encoding="utf-8")
        return {"kept": len(kept_lines), "dropped": dropped, "ttl_days": ttl_days}
    except Exception as e:
        return {"kept": 0, "dropped": 0, "error": str(e)}


def consolidate_episodes(max_promote: int = 12) -> dict:
    """Promote repeated episode themes into long-term facts and trim noise.

    Strategy (deterministic, no extra LLM call required):
    1. Score episodes by keyword frequency across the log.
    2. For high-frequency entity-like tokens, upsert graph nodes.
    3. Write a short daily summary fact under category 'session'.
    4. Optionally drop very old low-signal episodes (via forget_old_episodes).

    Idempotent for the same day: tracks last_run date.
    """
    from datetime import datetime
    from collections import Counter

    state = _load_consolidate_state()
    today = datetime.now().strftime("%Y-%m-%d")
    rows = _iter_episodes(max_lines=3000)
    if len(rows) < _MIN_EPISODES_TO_COMPACT and state.get("last_run") == today:
        return {"skipped": True, "reason": "already ran today or too few episodes", **episode_stats()}

    words: Counter = Counter()
    for ep in rows:
        text = f"{ep.get('text') or ''} {ep.get('summary') or ''}"
        for w in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_]{4,}", text.lower()):
            if w in {"this", "that", "with", "from", "have", "were", "para", "como",
                     "quando", "muito", "sobre", "user", "jarvis", "assistant"}:
                continue
            words[w] += 1

    promoted = 0
    for token, count in words.most_common(max_promote):
        if count < 3:
            break
        try:
            upsert_node(token, label=token, kind="topic")
            remember(
                key=f"topic_{token}"[:40],
                value=f"Mentioned frequently in recent episodes (count={count}).",
                category="derived",
            )
            promoted += 1
        except Exception:
            continue

    # Daily rollup fact
    try:
        summary = (
            f"Consolidated {len(rows)} episodes on {today}. "
            f"Top topics: {', '.join(t for t, _ in words.most_common(5)) or 'none'}."
        )
        remember(key=f"consolidate_{today}", value=summary, category="session")
    except Exception:
        pass

    forget_stats = forget_old_episodes()
    state["last_run"] = today
    state["facts_promoted"] = int(state.get("facts_promoted") or 0) + promoted
    state["episodes_dropped"] = int(state.get("episodes_dropped") or 0) + int(forget_stats.get("dropped") or 0)
    _save_consolidate_state(state)

    return {
        "promoted": promoted,
        "forget": forget_stats,
        "episodes": len(rows),
        "last_run": today,
    }


def detect_contradictions(limit: int = 20) -> list[dict]:
    """Naive hygiene pass: same key with conflicting values across categories.

    Returns a list of {key, values, categories} suspects. Does not auto-delete;
    the UI / model should ask the user which value wins.
    """
    memory = load_memory()
    by_key: dict[str, list[tuple[str, str]]] = {}
    for cat, entries in (memory or {}).items():
        if not isinstance(entries, dict):
            continue
        if cat.startswith("_"):
            continue
        for key, entry in entries.items():
            val = _entry_value(entry)
            if not val:
                continue
            by_key.setdefault(str(key).lower(), []).append((cat, val))

    suspects: list[dict] = []
    for key, pairs in by_key.items():
        unique_vals = {v.strip().lower() for _, v in pairs if v.strip()}
        if len(unique_vals) > 1:
            suspects.append({
                "key": key,
                "values": [{"category": c, "value": v} for c, v in pairs],
            })
        if len(suspects) >= limit:
            break
    return suspects


def memory_hygiene_report() -> str:
    """Human-readable report for the model or UI."""
    stats = episode_stats()
    cons = _load_consolidate_state()
    contras = detect_contradictions(limit=8)
    lines = [
        f"Episodes: {stats.get('episodes', 0)} | graph nodes: {stats.get('graph_nodes', 0)} | edges: {stats.get('graph_edges', 0)}",
        f"Last consolidate: {cons.get('last_run') or 'never'} (promoted={cons.get('facts_promoted', 0)}, dropped={cons.get('episodes_dropped', 0)})",
    ]
    if contras:
        lines.append(f"Possible contradictions: {len(contras)}")
        for c in contras[:5]:
            vals = "; ".join(f"{v['category']}={v['value'][:60]}" for v in c["values"][:3])
            lines.append(f"  - {c['key']}: {vals}")
    else:
        lines.append("No obvious contradictions detected.")
    return "\n".join(lines)
