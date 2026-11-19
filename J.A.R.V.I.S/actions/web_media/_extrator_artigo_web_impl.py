
"""Extrator reader-mode de artigos web para Markdown."""
from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urlparse

from core.outcome import ask, done, failed

try:
    from core.action_hardening import project_root, safe_url, sanitize_filename
except Exception:
    def project_root() -> Path:
        return Path(__file__).resolve().parents[3]
    def safe_url(url: str) -> str:
        return url
    def sanitize_filename(name: str, max_len: int = 120) -> str:
        return re.sub(r"[^\w\-. ]+", "_", name)[:max_len]

try:
    import requests
except Exception:
    requests = None


def _fetch(url: str) -> str:
    if requests is None:
        raise RuntimeError("requests nao instalado")
    r = requests.get(url, timeout=15, headers={"User-Agent": "JARVIS-Reader/1.0"})
    r.raise_for_status()
    return r.text


def _extract(html: str, url: str) -> tuple[str, str]:
    title = url
    # trafilatura
    try:
        import trafilatura  # type: ignore
        downloaded = trafilatura.extract(html, include_comments=False, include_tables=False)
        if downloaded and len(downloaded) > 80:
            try:
                meta = trafilatura.extract_metadata(html)
                if meta and getattr(meta, "title", None):
                    title = meta.title
            except Exception:
                pass
            return title, downloaded
    except Exception:
        pass
    # bs4
    try:
        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        article = soup.find("article") or soup.body
        text = article.get_text("\n", strip=True) if article else soup.get_text("\n", strip=True)
        if text and len(text) > 80:
            return title, text
    except Exception:
        pass
    # native density: strip tags
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return title, text


def _to_markdown(title: str, body: str) -> str:
    lines = [f"# {title}", ""]
    for para in re.split(r"\n{2,}", body):
        p = para.strip()
        if p:
            lines.append(p)
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def _read_minutes(text: str) -> float:
    words = len(re.findall(r"\w+", text))
    return round(max(1.0, words / 200.0), 1)


def run(parameters=None, **_ctx) -> str:
    params = dict(parameters or {})
    url = str(params.get("url") or "").strip()
    if not url:
        return ask("extrator_artigo_web", "Informe url=")
    try:
        url = safe_url(url)
    except Exception as e:
        return failed("extrator_artigo_web", str(e))
    host = (urlparse(url).hostname or "").lower()
    if host in ("localhost", "127.0.0.1") or host.startswith("192.168."):
        return failed("extrator_artigo_web", "SSRF bloqueado")
    try:
        html = _fetch(url)
        title, body = _extract(html, url)
    except Exception as e:
        return failed("extrator_artigo_web", f"extracao falhou: {e}")
    md = _to_markdown(title, body)
    minutes = _read_minutes(body)
    saved = None
    if str(params.get("salvar_na_memoria") or params.get("save") or "").lower() in ("1", "true", "sim", "yes"):
        cat = sanitize_filename(str(params.get("categoria") or "artigos"))
        docs = project_root() / "memory" / "knowledge_docs" / cat
        docs.mkdir(parents=True, exist_ok=True)
        fname = sanitize_filename(title) or "artigo"
        path = docs / f"{fname[:80]}.md"
        front = f"---\ntitle: {title}\nsource: {url}\nfetched: {time.time()}\n---\n\n"
        path.write_text(front + md, encoding="utf-8")
        saved = str(path)
    return done(
        "extrator_artigo_web",
        title=title,
        url=url,
        read_minutes=minutes,
        markdown=md[:6000],
        saved_path=saved,
        chars=len(body),
    )
