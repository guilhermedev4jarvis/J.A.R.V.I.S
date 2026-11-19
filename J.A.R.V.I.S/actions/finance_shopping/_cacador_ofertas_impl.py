
"""cacador_ofertas — alertas de preço com worker a cada 6h."""
from __future__ import annotations
import json, re, threading, time
from pathlib import Path
from typing import Any
from core.outcome import done, ask
from actions.security._security_vision import audit, send_telegram, speak_short

_PATH = Path(__file__).resolve().parents[2] / "memory" / "ofertas_vigiadas.json"
_lock = threading.Lock()
_worker = {"thread": None, "stop": threading.Event()}

def _load() -> dict:
    if not _PATH.is_file():
        return {"items": []}
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"items": []}

def _save(data: dict) -> None:
    with _lock:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _extract_price(text: str) -> float | None:
    m = re.search(r"(?:R\$\s*)?(\d+[.,]\d{2}|\d+)", text.replace(".", "").replace(",", ".") if False else text)
    # simpler
    m = re.search(r"(\d+[.,]\d{2})", text)
    if not m:
        m = re.search(r"(\d{2,6})", text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))

def _probe(query: str) -> tuple[float | None, str]:
    blob = ""
    try:
        import actions.web_media.web_search as web_search
        r = web_search.web_search(parameters={"query": query + " preço", "limit": 5})
        blob = str(r)
    except Exception as e:
        audit("oferta_search_fail", tool="cacador_ofertas", extra={"error": str(e)[:100]})
        try:
            import requests
            r = requests.get("https://duckduckgo.com/html/", params={"q": query + " preço"}, timeout=15)
            blob = r.text[:5000]
        except Exception as e2:
            return None, str(e2)[:120]
    return _extract_price(blob), blob[:240]

def _check_all(player=None):
    data = _load()
    changed = False
    for it in data.get("items") or []:
        if it.get("hit"):
            continue
        price, _ = _probe(it.get("query") or "")
        if price is None:
            continue
        it["last_price"] = price
        it["last_check"] = time.time()
        target = float(it.get("target") or 0)
        if target and price <= target:
            it["hit"] = True
            msg = f"Oferta: {it.get('query')} por ~R$ {price:.2f} (meta {target:.2f})."
            speak_short("Encontrei uma oferta na sua meta, Senhor.", player=player)
            send_telegram("*Radar de ofertas*\n" + msg, markdown=True)
            audit("oferta_hit", tool="cacador_ofertas", extra={"query": it.get("query"), "price": price})
        changed = True
    if changed:
        _save(data)

def _loop(player=None):
    while not _worker["stop"].is_set():
        try:
            _check_all(player=player)
        except Exception as e:
            audit("oferta_loop_err", tool="cacador_ofertas", extra={"error": str(e)[:120]})
        _worker["stop"].wait(6 * 3600)

def start_worker(player=None) -> bool:
    if _worker["thread"] and _worker["thread"].is_alive():
        return True
    _worker["stop"] = threading.Event()
    t = threading.Thread(target=_loop, args=(player,), daemon=True, name="cacador-ofertas")
    _worker["thread"] = t
    t.start()
    return True

def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "list").lower()
    query = str(p.get("query") or p.get("text") or p.get("topic") or "").strip()
    target = p.get("value")
    if action == "start_worker":
        return done("cacador_ofertas", worker=start_worker(player))
    if action == "stop_worker":
        _worker["stop"].set()
        return done("cacador_ofertas", worker=False)
    if action == "check_now":
        _check_all(player=player)
        return done("cacador_ofertas", action="check_now", ok=True)
    if action in ("watch", "vigiar", "monitorar"):
        if not query:
            return ask("cacador_ofertas", "Qual produto ou passagem vigiar, Senhor?")
        try:
            target_f = float(str(target).replace(",", ".")) if target not in (None, "") else 0.0
        except Exception:
            target_f = 0.0
        data = _load()
        data.setdefault("items", []).append({"query": query, "target": target_f, "hit": False})
        _save(data)
        start_worker(player)
        speak_short("Vigilância de preço ativada, Senhor.", player=player)
        return done("cacador_ofertas", action="watch", query=query, target=target_f)
    if action == "remove" and query:
        data = _load()
        data["items"] = [x for x in data.get("items") or [] if query.lower() not in str(x.get("query","")).lower()]
        _save(data)
        return done("cacador_ofertas", action="remove", query=query)
    data = _load()
    return done("cacador_ofertas", action="list", items=data.get("items") or [],
                worker=bool(_worker["thread"] and _worker["thread"].is_alive()))



def scan_lista_compras_deals(min_drop_pct: float = 10.0) -> list[dict]:
    """Compare lista_compras items against memory/price_history.json."""
    from pathlib import Path as _P
    import json as _json
    base = _P(__file__).resolve().parents[1]
    lista_path = base / "memory" / "lista_compras.json"
    hist_path = base / "memory" / "price_history.json"
    deals = []
    try:
        lista = _json.loads(lista_path.read_text(encoding="utf-8")) if lista_path.is_file() else {}
    except Exception:
        lista = {}
    items = lista.get("items") or lista.get("lista") or []
    if isinstance(items, dict):
        items = list(items.values())
    try:
        hist = _json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.is_file() else {"prices": {}}
    except Exception:
        hist = {"prices": {}}
    prices = hist.get("prices") or hist
    try:
        from core.event_bus import publish as _eb
    except Exception:
        def _eb(*a, **k):
            pass
    for it in items:
        if isinstance(it, str):
            name, cat = it, "geral"
        else:
            name = str((it or {}).get("name") or (it or {}).get("item") or it)
            cat = str((it or {}).get("category") or "geral")
        key = name.lower().strip()
        entry = prices.get(key) or {}
        avg = float(entry.get("avg") or entry.get("mean") or 0)
        current = float(entry.get("current") or entry.get("last") or 0)
        link = str(entry.get("url") or entry.get("link") or "")
        if avg <= 0 or current <= 0:
            try:
                cur, link2 = _probe(name)
                current = float(cur or 0)
                link = link or (link2 or "")
            except Exception:
                continue
        if avg > 0 and current > 0 and current <= avg * (1.0 - min_drop_pct / 100.0):
            deal = {
                "item_name": name,
                "category": cat,
                "price": current,
                "avg": avg,
                "drop_pct": round((1 - current / avg) * 100, 1),
                "link": link,
            }
            deals.append(deal)
            _eb("shopping.deal_found", **deal)
            try:
                msg = "Oferta: %s: R$ %.2f (-%.1f%% vs media)\n%s" % (
                    name, current, deal["drop_pct"], link
                )
                send_telegram(msg, markdown=True)
            except Exception:
                pass
    return deals

