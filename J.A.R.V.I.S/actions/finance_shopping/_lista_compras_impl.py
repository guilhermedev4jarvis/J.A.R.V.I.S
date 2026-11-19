
"""lista_compras — JSON categorizado Mercado/Farmácia/Casa."""
from __future__ import annotations
import json, re, threading
from pathlib import Path
try:
    from core.event_bus import publish as _eb_pub
except Exception:
    def _eb_pub(*a, **k): pass
from core.outcome import done, ask
from actions.security._security_vision import speak_short

_PATH = Path(__file__).resolve().parents[2] / "memory" / "lista_compras.json"
_lock = threading.Lock()

def _load():
    if not _PATH.is_file():
        return {"items": []}
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"items": []}

def _save(data):
    with _lock:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _cat(item: str) -> str:
    low = item.lower()
    if any(x in low for x in ("remédio", "remedio", "farmácia", "farmacia", "vitamina", "dorflex")):
        return "Farmácia"
    if any(x in low for x in ("sabão", "detergente", "esponja", "papel hig", "limpeza")):
        return "Casa"
    return "Mercado"

def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "list").lower()
    item = str(p.get("item") or p.get("text") or p.get("query") or "").strip()
    data = _load()
    if action in ("add", "adicionar") and item:
        cat = str(p.get("category") or _cat(item))
        data.setdefault("items", []).append({"item": item, "category": cat})
        _save(data)
        speak_short(f"Incluí {item} na lista, Senhor.", player=player)
        return done("lista_compras", action="add", item=item, category=cat, total=len(data["items"]))
    if action in ("clear", "limpar"):
        _save({"items": []})
        speak_short("Lista de compras limpa, Senhor.", player=player)
        return done("lista_compras", action="clear", total=0)
    if action in ("remove", "remover") and item:
        data["items"] = [x for x in data.get("items", []) if x.get("item", "").lower() != item.lower()]
        _save(data)
        return done("lista_compras", action="remove", item=item, total=len(data["items"]))
    # list
    items = data.get("items") or []
    if not items:
        speak_short("A lista está vazia, Senhor.", player=player)
        return done("lista_compras", action="list", items=[], total=0)
    by = {}
    for it in items:
        by.setdefault(it.get("category") or "Outros", []).append(it.get("item"))
    summary = "; ".join(f"{k}: {', '.join(v)}" for k, v in by.items())
    speak_short(f"Lista com {len(items)} itens, Senhor.", player=player)
    return done("lista_compras", action="list", items=items, by_category=by, summary=summary, total=len(items))


def _emit_item_added(item_name: str, category: str = "geral") -> None:
    try:
        from datetime import datetime
        _eb_pub(
            "shopping.item_added",
            item_name=item_name,
            category=category or "geral",
            added_at=datetime.now().isoformat(timespec="seconds"),
        )
    except Exception:
        pass
