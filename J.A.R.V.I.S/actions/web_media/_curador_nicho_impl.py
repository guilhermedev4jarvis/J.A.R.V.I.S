
"""curador_nicho — interesses + boletim filtrado."""
from __future__ import annotations
import json, threading
from pathlib import Path
from core.outcome import done, ask
from actions.security._security_vision import speak_short

_PATH = Path(__file__).resolve().parents[2] / "memory" / "nichos.json"
_lock = threading.Lock()

def _load():
    if not _PATH.is_file():
        return {"topics": []}
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"topics": []}

def _save(data):
    with _lock:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "bulletin").lower()
    topic = str(p.get("topic") or p.get("query") or p.get("text") or "").strip()
    data = _load()
    if action in ("follow", "acompanhar") and topic:
        if topic not in data.get("topics", []):
            data.setdefault("topics", []).append(topic)
            _save(data)
        speak_short(f"Passarei a acompanhar {topic}, Senhor.", player=player)
        return done("curador_nicho", action="follow", topic=topic, topics=data["topics"])
    if action == "unfollow" and topic:
        data["topics"] = [t for t in data.get("topics", []) if t.lower() != topic.lower()]
        _save(data)
        return done("curador_nicho", action="unfollow", topics=data["topics"])
    if action == "list":
        return done("curador_nicho", topics=data.get("topics") or [])
    topics = data.get("topics") or ([topic] if topic else [])
    if not topics:
        return ask("curador_nicho", "Qual nicho devo acompanhar, Senhor?")
    chunks = []
    for t in topics[:5]:
        try:
            from .web_search import web_search
            chunks.append(str(web_search(parameters={"query": t + " notícias", "limit": 3}))[:400])
        except Exception:
            try:
                from .noticias_brasil import noticias_brasil
                chunks.append(str(noticias_brasil(parameters={"query": t}))[:400])
            except Exception:
                chunks.append(f"{t}: sem fonte no momento")
    blob = "\n".join(chunks)
    try:
        from core.llm_client import call_llm_text
        bulletin = call_llm_text(
            "Boletim executivo curto (5-7 frases), sem repetição, português elegante:\n" + blob,
            system="Curador de nicho.",
            timeout=40,
        ) or blob[:600]
    except Exception:
        bulletin = blob[:600]
    speak_short("Boletim do seu nicho pronto, Senhor.", player=player)
    return done("curador_nicho", action="bulletin", bulletin=bulletin, topics=topics)
