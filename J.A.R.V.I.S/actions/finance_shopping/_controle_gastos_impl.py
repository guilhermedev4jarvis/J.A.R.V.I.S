
"""controle_gastos — CSV de despesas com totais."""
from __future__ import annotations
import csv, re, threading
from datetime import datetime, timedelta
from pathlib import Path
from core.outcome import done, ask, failed
from actions.security._security_vision import speak_short

_PATH = Path(__file__).resolve().parents[2] / "memory" / "gastos.csv"
_lock = threading.Lock()

def _ensure():
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _PATH.is_file():
        with _PATH.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["date", "amount", "category", "description"])

def _parse_amount(text: str) -> float:
    m = re.search(r"(\d+[.,]?\d*)", text.replace("reais", " "))
    if not m:
        return 0.0
    return float(m.group(1).replace(",", "."))

def _rows():
    _ensure()
    with _PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "summary").lower()
    if action in ("add", "anotar"):
        desc = str(p.get("text") or p.get("description") or p.get("query") or "")
        amount = p.get("value")
        if amount is None or amount == "":
            amount = _parse_amount(desc)
        else:
            amount = float(str(amount).replace(",", "."))
        cat = str(p.get("category") or "geral")
        if amount <= 0:
            return ask("controle_gastos", "Qual valor do gasto, Senhor?")
        _ensure()
        with _lock:
            with _PATH.open("a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([datetime.now().date().isoformat(), f"{amount:.2f}", cat, desc])
        speak_short(f"Registrei {amount:.2f} reais, Senhor.", player=player)
        return done("controle_gastos", action="add", amount=amount, category=cat)
    rows = _rows()
    now = datetime.now()
    def in_range(d, days):
        try:
            dt = datetime.fromisoformat(d)
            return dt >= now - timedelta(days=days)
        except Exception:
            return False
    if action == "week":
        sel = [r for r in rows if in_range(r.get("date", ""), 7)]
    else:
        sel = [r for r in rows if (r.get("date") or "").startswith(now.strftime("%Y-%m"))]
    total = sum(float(r.get("amount") or 0) for r in sel)
    speak_short(f"Total de {total:.2f} reais no período, Senhor.", player=player)
    return done("controle_gastos", action=action or "month", total=round(total, 2), count=len(sel))
