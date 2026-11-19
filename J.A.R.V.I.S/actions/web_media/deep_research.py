"""
Action: deep_research — autonomous multi-step research agent.

Pipeline:
  1. Plan          → break the question into 3–5 focused search angles (Gemini FAST)
  2. Gather        → run those searches in parallel (DDG + optional Gemini grounding)
  3. Deep-read     → fetch full text of the most promising pages (requests + BS4)
  4. Synthesize    → structured brief with sources (Gemini SMART)
  5. Optional save → write a markdown report under ~/Documents/JarvisResearch/

Returns a spoken-friendly summary; the full brief is in the tool result for the
model to paraphrase. Designed for questions that need more than a single search.
"""
from __future__ import annotations

import concurrent.futures
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

# ── Optional deps (already in project requirements) ──────────────────────────
try:
    import requests
    from bs4 import BeautifulSoup
    _HTTP = True
except ImportError:
    _HTTP = False

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS  # type: ignore
    except ImportError:
        DDGS = None  # type: ignore

from core import gemini

# ── Constants ────────────────────────────────────────────────────────────────
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_FETCH_TIMEOUT = 8
_MAX_PAGE_CHARS = 6000
_MAX_ANGLES = 5
_RESULTS_PER_ANGLE = 4
_MAX_PAGES_TO_READ = 4
_BLOCKED_DOMAINS = {
    "youtube.com", "youtu.be", "facebook.com", "instagram.com",
    "twitter.com", "x.com", "tiktok.com", "pinterest.com",
    "reddit.com",  # often blocked / heavy JS
}


def _log(msg: str, player=None) -> None:
    print(f"[DeepResearch] {msg}")
    if player:
        try:
            player.write_log(f"JARVIS: {msg}")
        except Exception:
            pass


# ── Step 1: Plan search angles ───────────────────────────────────────────────

def _plan_angles(question: str, depth: str) -> list[str]:
    """Ask Gemini for focused search queries. Always returns at least the raw question."""
    n = 5 if depth == "deep" else 3
    prompt = (
        f"You are a research planner. Break this question into {n} short, "
        f"focused web-search queries that together cover the topic from different angles "
        f"(facts, recent developments, expert views, numbers, comparisons when relevant).\n\n"
        f"Question: {question}\n\n"
        f"Reply with ONLY a JSON array of strings, no markdown, no commentary.\n"
        f'Example: ["query one", "query two"]'
    )
    try:
        data = gemini.as_json(prompt, tier=gemini.FAST, timeout_ms=20_000)
        if isinstance(data, list):
            angles = [str(x).strip() for x in data if str(x).strip()]
            if angles:
                return angles[:_MAX_ANGLES]
        if isinstance(data, dict):
            for key in ("queries", "angles", "searches"):
                if isinstance(data.get(key), list):
                    angles = [str(x).strip() for x in data[key] if str(x).strip()]
                    if angles:
                        return angles[:_MAX_ANGLES]
    except Exception as e:
        print(f"[DeepResearch] plan failed: {e}")

    # Fallback: the question itself + a couple of naive variants
    return [
        question,
        f"{question} latest",
        f"{question} overview",
    ][:n]


# ── Step 2: Search ───────────────────────────────────────────────────────────

def _ddg_search(query: str, max_results: int = _RESULTS_PER_ANGLE) -> list[dict]:
    if DDGS is None:
        return []
    out: list[dict] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                out.append({
                    "title": r.get("title") or "",
                    "snippet": r.get("body") or "",
                    "url": r.get("href") or "",
                    "query": query,
                })
    except Exception as e:
        print(f"[DeepResearch] DDG error for '{query}': {e}")
    return out


def _gather_results(angles: list[str]) -> list[dict]:
    """Parallel search across all angles; dedupe by URL."""
    results: list[dict] = []
    seen: set[str] = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(angles) or 1)) as pool:
        futures = {pool.submit(_ddg_search, q): q for q in angles}
        for fut in concurrent.futures.as_completed(futures, timeout=25):
            try:
                batch = fut.result()
            except Exception:
                continue
            for item in batch:
                url = (item.get("url") or "").strip()
                if not url or url in seen:
                    continue
                domain = urlparse(url).netloc.lower().removeprefix("www.")
                if any(b in domain for b in _BLOCKED_DOMAINS):
                    continue
                seen.add(url)
                results.append(item)
    return results


# ── Step 3: Deep-read top pages ──────────────────────────────────────────────

def _looks_useful(url: str, title: str, snippet: str) -> float:
    """Rough score for which pages deserve a full fetch."""
    score = 1.0
    domain = urlparse(url).netloc.lower()
    # Prefer known knowledge sources
    for good in ("wikipedia.org", "gov", "edu", "bbc.", "reuters.", "nature.com",
                 "arxiv.org", "nih.gov", "who.int", "statista.", "britannica."):
        if good in domain:
            score += 2.0
    if len(snippet) > 120:
        score += 0.5
    if title:
        score += 0.3
    if url.rstrip("/").endswith((".pdf",)):
        score -= 1.0  # skip PDFs for now (need different parser)
    return score


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    # Prefer article / main
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = main.get_text(separator="\n", strip=True)
    # Collapse whitespace
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    text = "\n".join(lines)
    return text[:_MAX_PAGE_CHARS]


def _fetch_page(url: str) -> Optional[dict]:
    if not _HTTP:
        return None
    try:
        r = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"},
            timeout=_FETCH_TIMEOUT,
            allow_redirects=True,
        )
        if r.status_code != 200 or not r.text:
            return None
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "html" not in ctype and "text" not in ctype:
            return None
        text = _extract_text(r.text)
        if len(text) < 200:
            return None
        return {"url": url, "text": text, "length": len(text)}
    except Exception as e:
        print(f"[DeepResearch] fetch failed {url}: {e}")
        return None


def _deep_read(results: list[dict], limit: int = _MAX_PAGES_TO_READ) -> list[dict]:
    ranked = sorted(
        results,
        key=lambda r: _looks_useful(r.get("url", ""), r.get("title", ""), r.get("snippet", "")),
        reverse=True,
    )
    pages: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futs = [pool.submit(_fetch_page, r["url"]) for r in ranked[: limit + 2]]
        for fut in concurrent.futures.as_completed(futs, timeout=30):
            try:
                page = fut.result()
            except Exception:
                continue
            if page:
                # attach title from search if we can
                for r in ranked:
                    if r.get("url") == page["url"]:
                        page["title"] = r.get("title") or ""
                        break
                pages.append(page)
            if len(pages) >= limit:
                break
    return pages


# ── Step 4: Synthesize ───────────────────────────────────────────────────────

def _synthesize(question: str, results: list[dict], pages: list[dict], language: str) -> str:
    # Build evidence pack (bounded size)
    evidence_parts: list[str] = []
    for i, r in enumerate(results[:12], 1):
        evidence_parts.append(
            f"[{i}] {r.get('title','')}\n"
            f"    {r.get('snippet','')}\n"
            f"    URL: {r.get('url','')}"
        )
    for j, p in enumerate(pages, 1):
        evidence_parts.append(
            f"[PAGE {j}] {p.get('title') or p.get('url')}\n"
            f"{p.get('text','')[:4500]}\n"
            f"URL: {p.get('url','')}"
        )
    evidence = "\n\n".join(evidence_parts)[:28000]

    lang_line = (
        "Write the entire brief in Brazilian Portuguese."
        if language.lower().startswith("pt")
        else f"Write the entire brief in {language}."
    )

    prompt = f"""You are a rigorous research analyst. Using ONLY the evidence below, produce a clear research brief on the question.

QUESTION:
{question}

EVIDENCE:
{evidence}

RULES:
- {lang_line}
- Structure:
  1) Resposta direta (2–4 sentences that actually answer the question)
  2) Pontos-chave (5–8 bullet points with concrete facts, numbers, dates when available)
  3) Nuances / controvérsias (if any)
  4) Fontes (list the most important URLs you relied on)
- If evidence is weak or contradictory, say so explicitly.
- Do not invent facts that are not supported by the evidence.
- Keep the spoken-friendly core under ~250 words; fontes can be longer.
"""
    try:
        answer = gemini.text(prompt, tier=gemini.SMART, timeout_ms=90_000)
        if answer and len(answer.strip()) > 80:
            return answer.strip()
    except Exception as e:
        print(f"[DeepResearch] synthesize failed: {e}")

    # Fallback: compress search snippets
    if not results:
        return "Não encontrei evidências suficientes para responder com segurança."
    lines = [f"Pesquisa sobre: {question}", ""]
    for r in results[:6]:
        if r.get("title"):
            lines.append(f"• {r['title']}")
        if r.get("snippet"):
            lines.append(f"  {r['snippet'][:200]}")
        if r.get("url"):
            lines.append(f"  {r['url']}")
    return "\n".join(lines)


# ── Step 5: Optional save ────────────────────────────────────────────────────

def _save_report(question: str, brief: str) -> Optional[str]:
    try:
        base = Path.home() / "Documents" / "JarvisResearch"
        base.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r"[^\w\-]+", "_", question.lower())[:60].strip("_") or "research"
        path = base / f"{stamp}_{safe}.md"
        body = (
            f"# Pesquisa: {question}\n\n"
            f"*Gerado por MARK LXI — {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
            f"{brief}\n"
        )
        path.write_text(body, encoding="utf-8")
        return str(path)
    except Exception as e:
        print(f"[DeepResearch] save failed: {e}")
        return None


# ── Entry point ──────────────────────────────────────────────────────────────

def deep_research_action(
    parameters: dict,
    player=None,
    session_memory=None,
    speak=None,
    response=None,
) -> str:
    question = (parameters.get("question") or parameters.get("query") or "").strip()
    if not question:
        return (
            "Sir, preciso da pergunta de pesquisa. "
            "Exemplo: 'impactos da energia nuclear no Brasil em 2025'."
        )

    depth = (parameters.get("depth") or "normal").strip().lower()
    if depth not in ("quick", "normal", "deep"):
        depth = "normal"
    save = str(parameters.get("save") or "").lower() in ("1", "true", "yes", "sim")
    language = (parameters.get("language") or "Portuguese").strip()

    t0 = time.monotonic()
    _log(f"Starting research ({depth}): {question[:80]}", player)

    # 1. Plan
    angles = _plan_angles(question, depth)
    _log(f"Angles ({len(angles)}): {angles}", player)

    # 2. Gather
    results = _gather_results(angles)
    _log(f"Search hits: {len(results)}", player)

    if not results:
        return (
            "Sir, a busca não retornou resultados úteis. "
            "Pode reformular a pergunta ou tentar mais tarde."
        )

    # 3. Deep-read (skip on quick)
    pages: list[dict] = []
    if depth in ("normal", "deep") and _HTTP:
        n_pages = 2 if depth == "normal" else _MAX_PAGES_TO_READ
        pages = _deep_read(results, limit=n_pages)
        _log(f"Pages read: {len(pages)}", player)

    # 4. Synthesize
    brief = _synthesize(question, results, pages, language)

    # 5. Save
    saved = None
    if save or depth == "deep":
        saved = _save_report(question, brief)

    elapsed = time.monotonic() - t0
    footer_bits = [f"{len(results)} fontes indexadas", f"{len(pages)} páginas lidas", f"{elapsed:.0f}s"]
    if saved:
        footer_bits.append(f"salvo em {saved}")
    footer = " · ".join(footer_bits)

    # Spoken-friendly: the model will paraphrase; include full brief in result
    msg = (
        f"Pesquisa concluída sobre: {question}\n\n"
        f"{brief}\n\n"
        f"— ({footer})"
    )
    _log(f"Done in {elapsed:.1f}s", player)
    return msg


TOOL = {
    "name": "deep_research",
    "description": (
        "Autonomous multi-step research agent. Use for complex questions that need "
        "more than a single web search: comparisons, 'what is the current state of X', "
        "technical deep-dives, market/context overviews. "
        "It plans several search angles, gathers results, reads the best pages, "
        "and synthesizes a structured brief with sources. "
        "Prefer this over plain web_search when the user asks to 'pesquisar a fundo', "
        "'faz uma pesquisa', 'me explica com fontes', 'compara em detalhe'. "
        "Do NOT use for simple factual lookups (use web_search) or for controlling the browser UI."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "question": {
                "type": "STRING",
                "description": "The research question in natural language (required)",
            },
            "depth": {
                "type": "STRING",
                "description": (
                    "quick = search only, no page fetch; "
                    "normal = search + a few pages (default); "
                    "deep = more angles, more pages, always saves a report"
                ),
            },
            "save": {
                "type": "STRING",
                "description": "true/false — save markdown report under ~/Documents/JarvisResearch/",
            },
            "language": {
                "type": "STRING",
                "description": "Language for the brief (default Portuguese)",
            },
        },
        "required": ["question"],
    },
    "handler": deep_research_action,
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
}
