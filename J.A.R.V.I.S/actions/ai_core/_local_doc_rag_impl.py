"""Read/summarize/search local documents under sandbox-allowed paths."""
from __future__ import annotations
from core import knowledge_store

import re
from pathlib import Path
from typing import Optional

from core.outcome import ask, done, failed

_MAX_CHARS = 120_000
_EXTS = {".txt", ".md", ".markdown", ".log", ".csv", ".json", ".pdf", ".docx"}


def _sandbox_ok(path: Path) -> tuple[bool, str]:
    try:
        from core import sandbox
        if hasattr(sandbox, "check_path"):
            ok = sandbox.check_path(str(path))
            if ok is False:
                return False, "path blocked by sandbox"
        if hasattr(sandbox, "is_allowed"):
            if not sandbox.is_allowed(str(path)):
                return False, "path not allowed"
    except Exception:
        # conservative: only home + project
        home = Path.home().resolve()
        try:
            path.resolve().relative_to(home)
        except Exception:
            root = Path(__file__).resolve().parents[2]
            try:
                path.resolve().relative_to(root)
            except Exception:
                return False, "path outside home/project"
    return True, ""


def _read_text(path: Path) -> str:
    suf = path.suffix.lower()
    if suf in {".txt", ".md", ".markdown", ".log", ".csv", ".json"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suf == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
            reader = PdfReader(str(path))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception:
            try:
                import PyPDF2  # type: ignore
                reader = PyPDF2.PdfReader(str(path))
                return "\n".join((p.extract_text() or "") for p in reader.pages)
            except Exception as e:
                raise RuntimeError(f"PDF read failed: {e}") from e
    if suf == ".docx":
        try:
            import docx  # type: ignore
            d = docx.Document(str(path))
            return "\n".join(p.text for p in d.paragraphs)
        except Exception as e:
            raise RuntimeError(f"DOCX read failed: {e}") from e
    raise RuntimeError(f"unsupported extension: {suf}")


def _redact(text: str) -> str:
    try:
        from core import redaction
        if hasattr(redaction, "redact"):
            return redaction.redact(text)
        if hasattr(redaction, "mask"):
            return redaction.mask(text)
    except Exception:
        pass
    # minimal local mask
    text = re.sub(r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*\S+", r"\1=***", text)
    return text


def _summarize(text: str, max_sentences: int = 8) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return "(empty document)"
    return " ".join(parts[:max_sentences])


def _search(text: str, query: str, limit: int = 5) -> list[str]:
    q = query.lower().strip()
    if not q:
        return []
    hits = []
    for i, line in enumerate(text.splitlines()):
        if q in line.lower():
            hits.append(f"L{i+1}: {line.strip()[:240]}")
            if len(hits) >= limit:
                break
    return hits


def run(parameters: Optional[dict] = None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or p.get("mode") or "read").strip().lower()
    path_s = str(p.get("path") or p.get("file") or p.get("file_path") or "").strip()
    query = str(p.get("query") or p.get("question") or "").strip()

    if not path_s:
        return ask("local_doc_rag", "Qual o caminho do documento local?")

    path = Path(path_s).expanduser()
    ok, why = _sandbox_ok(path)
    if not ok:
        return failed("local_doc_rag", why, path=path_s)
    if not path.is_file():
        return failed("local_doc_rag", "file not found", path=path_s)
    if path.suffix.lower() not in _EXTS:
        return failed("local_doc_rag", f"unsupported type {path.suffix}", path=path_s)

    try:
        raw = _read_text(path)[:_MAX_CHARS]
        text = _redact(raw)
    except Exception as e:
        return failed("local_doc_rag", str(e), path=path_s)

    if action in ("read", "open"):
        preview = text[:2000]
        return done("local_doc_rag", op="read", path=str(path), chars=len(text), preview=preview)

    if action in ("summarize", "summary", "resumo"):
        return done("local_doc_rag", op="summarize", path=str(path), summary=_summarize(text))

    if action in ("search", "ask", "query"):
        if not query:
            return ask("local_doc_rag", "O que procurar ou perguntar no documento?")
        hits = _search(text, query)
        # naive Q&A: return matching lines + short summary context
        return done(
            "local_doc_rag",
            op="search",
            path=str(path),
            query=query,
            hits=len(hits),
            results=" | ".join(hits) if hits else "(no hits)",
            context=_summarize(text, 4),
        )

    return failed("local_doc_rag", f"unknown action {action}")
def _rag_local_query(query: str) -> dict:
    try:
        knowledge_store.reindex_all()
    except Exception:
        pass
    return knowledge_store.answer_with_citations(query, limit=4)


