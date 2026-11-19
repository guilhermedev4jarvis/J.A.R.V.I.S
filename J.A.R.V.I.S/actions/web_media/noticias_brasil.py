"""
Plugin: notícias do Brasil (resumo de 2–3 manchetes).

Trigger: "notícias", "notícias de hoje", "o que está acontecendo", "manchetes", etc.
"""

from __future__ import annotations

import json
import re
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

# RSS feeds (no API key needed)
_FEEDS = {
    "geral": "https://g1.globo.com/rss/g1/",
    "politica": "https://g1.globo.com/rss/g1/politica/",
    "economia": "https://g1.globo.com/rss/g1/economia/",
    "tecnologia": "https://g1.globo.com/rss/g1/tecnologia/",
    "esportes": "https://ge.globo.com/rss/ge/",
    "mundo": "https://g1.globo.com/rss/g1/mundo/",
}


def _fetch_rss(url: str, limit: int = 5) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/1.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)
    items = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        desc = (item.findtext("description") or "").strip()
        # Strip HTML tags from description
        desc = re.sub(r"<[^>]+>", "", desc).strip()
        if title:
            items.append({"title": title, "desc": desc[:180]})
    return items


def run(parameters: dict, player=None, session_memory=None) -> str:
    tema = (parameters.get("tema") or "geral").strip().lower()
    # Map common Portuguese words
    aliases = {
        "política": "politica", "politica": "politica",
        "economia": "economia", "tecnologia": "tecnologia", "tech": "tecnologia",
        "esporte": "esportes", "esportes": "esportes", "futebol": "esportes",
        "mundo": "mundo", "internacional": "mundo",
        "geral": "geral", "": "geral",
    }
    key = aliases.get(tema, "geral")
    url = _FEEDS.get(key, _FEEDS["geral"])

    try:
        items = _fetch_rss(url, limit=4)
        if not items:
            return "Sir, não consegui obter manchetes no momento."

        # Pick top 2–3
        chosen = items[:3]
        parts = []
        for i, it in enumerate(chosen, 1):
            line = it["title"]
            if it["desc"] and len(it["desc"]) > 20:
                line += f" — {it['desc']}"
            parts.append(f"{i}. {line}")

        result = "Aqui vão as principais notícias: " + " ".join(parts)
        # Keep it speakable
        if len(result) > 500:
            result = "Aqui vão as principais notícias: " + " ".join(
                f"{i}. {it['title']}" for i, it in enumerate(chosen, 1)
            )

        if player:
            try:
                player.write_log(f"JARVIS: {result}")
            except Exception:
                pass
        return result

    except Exception as e:
        msg = f"Sir, falha ao buscar notícias: {e}"
        if player:
            try:
                player.write_log(f"JARVIS: {msg}")
            except Exception:
                pass
        return msg

# ── Unified action contract (migrated from plugins/) ──────────────────────────

def noticias_brasil(parameters=None, player=None, session_memory=None, **_ctx):
    """TOOL handler — delegates to legacy run()."""
    params = parameters if isinstance(parameters, dict) else {}
    try:
        return run(params, player=player, session_memory=session_memory)
    except TypeError:
        try:
            return run(params, player=player)
        except TypeError:
            return run(params)


TOOL = {
    "name": "noticias_brasil",
    "description": ('Fetches and summarizes 2–3 current Brazilian news headlines.  Call this whenever the user asks for news, notícias, manchetes,   ,  , or a brief news update.  Do NOT use web_search for general Brazilian news — use this tool instead.  Returns a short spoken summary in Portuguese.'),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "tema": {
                "type": "STRING",
                "description": "Optional topic filter, e.g. política, economia, tecnologia, esportes. Leave empty for general headlines.",
            },
        },
        "required": [],
    },
    "handler": noticias_brasil,
    "tier": "plugin",
    "risk": "review",
}
