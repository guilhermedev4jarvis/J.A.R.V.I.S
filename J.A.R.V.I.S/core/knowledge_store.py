"""core/knowledge_store.py — offline knowledge base with SQLite FTS5 + pure BM25 ranking.

Indexes Markdown/JSON under memory/knowledge_docs/ into memory/knowledge_base.db.
No network, no heavy ML deps required.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import threading
from collections import Counter
from pathlib import Path
from typing import Any, Optional

_BASE = Path(__file__).resolve().parents[1]
_DOCS = _BASE / "memory" / "knowledge_docs"
_DB = _BASE / "memory" / "knowledge_base.db"
_lock = threading.RLock()
_query_cache: dict[str, list[dict]] = {}
_CACHE_MAX = 64

_TOKEN_RE = re.compile(r"[a-záàâãéêíóôõúç0-9]{2,}", re.I)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _connect() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            title TEXT,
            source TEXT,
            content_hash TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY,
            doc_id INTEGER,
            chunk_index INTEGER,
            text TEXT,
            token_count INTEGER,
            FOREIGN KEY(doc_id) REFERENCES documents(id)
        )
        """
    )
    # FTS5 virtual table
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            text,
            content='chunks',
            content_rowid='id',
            tokenize='porter'
        )
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.id, old.text);
        END
        """
    )
    return conn


def chunk_text(text: str, size: int = 700, overlap: int = 120) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + size])
        i += max(1, size - overlap)
    return chunks


def _doc_title(path: Path, body: str) -> str:
    for line in body.splitlines()[:15]:
        if line.startswith("#"):
            return line.lstrip("# ").strip()[:120]
    return path.stem.replace("_", " ")


def index_document(path: Path, conn: Optional[sqlite3.Connection] = None) -> int:
    own = conn is None
    conn = conn or _connect()
    try:
        body = path.read_text(encoding="utf-8", errors="ignore")
        h = hashlib.sha256(body.encode("utf-8")).hexdigest()
        row = conn.execute("SELECT id, content_hash FROM documents WHERE path=?", (str(path),)).fetchone()
        if row and row["content_hash"] == h:
            return 0
        if row:
            conn.execute("DELETE FROM chunks WHERE doc_id=?", (row["id"],))
            conn.execute("DELETE FROM documents WHERE id=?", (row["id"],))
        from datetime import datetime
        cur = conn.execute(
            "INSERT INTO documents(path, title, source, content_hash, updated_at) VALUES (?,?,?,?,?)",
            (str(path), _doc_title(path, body), path.name, h, datetime.now().isoformat(timespec="seconds")),
        )
        doc_id = cur.lastrowid
        n = 0
        for i, ch in enumerate(chunk_text(body)):
            toks = _tokenize(ch)
            conn.execute(
                "INSERT INTO chunks(doc_id, chunk_index, text, token_count) VALUES (?,?,?,?)",
                (doc_id, i, ch, len(toks)),
            )
            n += 1
        conn.commit()
        return n
    finally:
        if own:
            conn.close()


def reindex_all(docs_dir: Optional[Path] = None) -> dict[str, Any]:
    docs_dir = docs_dir or _DOCS
    docs_dir.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = _connect()
        try:
            total_chunks = 0
            files = 0
            for p in sorted(docs_dir.rglob("*")):
                if p.suffix.lower() not in (".md", ".txt", ".json"):
                    continue
                if p.name.startswith("."):
                    continue
                total_chunks += index_document(p, conn)
                files += 1
            _query_cache.clear()
            return {"files": files, "chunks_written": total_chunks, "db": str(_DB)}
        finally:
            conn.close()


def _bm25_score(query_tokens: list[str], doc_tokens: list[str], avgdl: float, df: dict[str, int], N: int, k1: float = 1.5, b: float = 0.75) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    tf = Counter(doc_tokens)
    dl = len(doc_tokens)
    score = 0.0
    for term in set(query_tokens):
        f = tf.get(term, 0)
        if f == 0:
            continue
        n_qi = df.get(term, 0) or 1
        idf = math.log(1 + (N - n_qi + 0.5) / (n_qi + 0.5))
        denom = f + k1 * (1 - b + b * dl / max(avgdl, 1.0))
        score += idf * (f * (k1 + 1)) / denom
    return score


def search(query: str, limit: int = 5, use_cache: bool = True) -> list[dict]:
    q = (query or "").strip()
    if not q:
        return []
    cache_key = f"{q}::{limit}"
    if use_cache and cache_key in _query_cache:
        return list(_query_cache[cache_key])

    tokens = _tokenize(q)
    results: list[dict] = []
    with _lock:
        conn = _connect()
        try:
            # FTS5 first
            fts_rows = []
            try:
                # quote tokens for FTS
                q_fts = " ".join(tokens) if tokens else q
                fts_rows = conn.execute(
                    """
                    SELECT c.id, c.text, c.doc_id, d.title, d.path, d.source,
                           bm25(chunks_fts) AS rank
                    FROM chunks_fts
                    JOIN chunks c ON c.id = chunks_fts.rowid
                    JOIN documents d ON d.id = c.doc_id
                    WHERE chunks_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (q_fts, limit * 3),
                ).fetchall()
            except sqlite3.OperationalError:
                fts_rows = []

            if fts_rows:
                for r in fts_rows[:limit]:
                    results.append(
                        {
                            "text": r["text"],
                            "title": r["title"],
                            "source": r["source"],
                            "path": r["path"],
                            "score": float(-(r["rank"] or 0)),
                            "method": "fts5",
                        }
                    )
            else:
                # pure BM25 fallback over all chunks (fine for modest corpora)
                rows = conn.execute(
                    """
                    SELECT c.id, c.text, c.token_count, d.title, d.path, d.source
                    FROM chunks c JOIN documents d ON d.id = c.doc_id
                    """
                ).fetchall()
                if not rows:
                    return []
                tokenized = []
                df: Counter = Counter()
                total_len = 0
                for r in rows:
                    toks = _tokenize(r["text"])
                    tokenized.append(toks)
                    total_len += len(toks)
                    df.update(set(toks))
                N = len(rows)
                avgdl = total_len / max(N, 1)
                scored = []
                for r, toks in zip(rows, tokenized):
                    s = _bm25_score(tokens, toks, avgdl, df, N)
                    if s > 0:
                        scored.append((s, r))
                scored.sort(key=lambda x: x[0], reverse=True)
                for s, r in scored[:limit]:
                    results.append(
                        {
                            "text": r["text"],
                            "title": r["title"],
                            "source": r["source"],
                            "path": r["path"],
                            "score": s,
                            "method": "bm25",
                        }
                    )
        finally:
            conn.close()

    if use_cache:
        if len(_query_cache) >= _CACHE_MAX:
            _query_cache.pop(next(iter(_query_cache)))
        _query_cache[cache_key] = list(results)
    return results


def answer_with_citations(query: str, limit: int = 4) -> dict:
    hits = search(query, limit=limit)
    if not hits:
        return {"ok": False, "answer": "Nada encontrado na base local, Senhor.", "citations": []}
    parts = []
    citations = []
    for i, h in enumerate(hits, 1):
        parts.append(h["text"][:500])
        citations.append({"n": i, "title": h.get("title"), "source": h.get("source"), "score": h.get("score")})
    answer = "Com base na base local:\n\n" + "\n\n".join(f"[{i}] {p}" for i, p in enumerate(parts, 1))
    return {"ok": True, "answer": answer, "citations": citations, "hits": len(hits)}
