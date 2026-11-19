
"""Rastreador e classificacao de historico de precos."""
from __future__ import annotations

import statistics
import time
from pathlib import Path
from typing import Any

from core.outcome import ask, done, failed

try:
    from core.action_hardening import atomic_write_json, project_root
except Exception:
    def project_root() -> Path:
        return Path(__file__).resolve().parents[3]
    def atomic_write_json(path, data, **kw):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        import json
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _path() -> Path:
    return project_root() / "memory" / "precos_monitorados.json"


def _load() -> dict:
    import json
    p = _path()
    if not p.is_file():
        return {"products": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {"products": {}}


def _save(data: dict) -> None:
    atomic_write_json(_path(), data)


def _classify(price: float, series: list[float]) -> str:
    if len(series) < 2:
        return "PRECO_NORMAL"
    avg = statistics.mean(series)
    med = statistics.median(series)
    mn = min(series)
    if price <= mn * 1.02 and price < avg * 0.9:
        return "EXCELENTE_OPORTUNIDADE"
    if price > avg * 1.15:
        return "ACIMA_DA_MEDIA"
    # possible cosmetic: slight drop after artificial high
    if len(series) >= 4 and max(series[-4:-1]) > avg * 1.2 and price < avg:
        return "POSSIVEL_MAQUIAGEM"
    if abs(price - med) / (med or 1) < 0.08:
        return "PRECO_NORMAL"
    return "PRECO_NORMAL"


def run(parameters=None, **_ctx) -> str:
    params = dict(parameters or {})
    action = str(params.get("action") or params.get("mode") or "listar").strip().lower()
    data = _load()
    products: dict = data.setdefault("products", {})

    if action in ("listar", "list"):
        summary = {k: {"n": len(v.get("history") or []), "last": (v.get("history") or [{}])[-1]} for k, v in products.items()}
        return done("comparador_preco_historico", products=list(products.keys()), summary=summary)

    if action in ("remover", "remove"):
        key = str(params.get("produto") or params.get("product") or params.get("name") or "").strip().lower()
        if key not in products:
            return failed("comparador_preco_historico", "produto nao encontrado")
        del products[key]
        _save(data)
        return done("comparador_preco_historico", action="remover", produto=key)

    if action in ("registrar", "add", "track"):
        nome = str(params.get("produto") or params.get("product") or params.get("name") or "").strip()
        if not nome:
            return ask("comparador_preco_historico", "Informe produto=")
        try:
            preco = float(str(params.get("preco") or params.get("price") or "0").replace(",", "."))
        except ValueError:
            return failed("comparador_preco_historico", "preco invalido")
        if preco <= 0:
            return failed("comparador_preco_historico", "preco deve ser > 0")
        key = nome.lower()
        entry = products.setdefault(key, {"name": nome, "history": []})
        point = {
            "price": preco,
            "store": str(params.get("loja") or params.get("store") or ""),
            "url": str(params.get("url") or ""),
            "ts": time.time(),
        }
        entry["history"].append(point)
        entry["history"] = entry["history"][-200:]
        series = [h["price"] for h in entry["history"]]
        label = _classify(preco, series)
        _save(data)
        return done("comparador_preco_historico", action="registrar", produto=nome, price=preco, classLabel=label)

    if action in ("analisar", "analyze", "stats"):
        key = str(params.get("produto") or params.get("product") or params.get("name") or "").strip().lower()
        if not key or key not in products:
            return failed("comparador_preco_historico", "produto nao encontrado")
        series = [float(h["price"]) for h in products[key].get("history") or []]
        if not series:
            return failed("comparador_preco_historico", "sem historico")
        last = series[-1]
        stats = {
            "min": min(series),
            "max": max(series),
            "avg": round(statistics.mean(series), 4),
            "median": round(statistics.median(series), 4),
            "count": len(series),
            "last": last,
            "variation_pct": round(((last - series[0]) / series[0]) * 100, 2) if series[0] else 0.0,
            "classLabel": _classify(last, series),
        }
        return done("comparador_preco_historico", action="analisar", produto=products[key].get("name"), **stats)

    return failed("comparador_preco_historico", f"action desconhecida: {action}")
