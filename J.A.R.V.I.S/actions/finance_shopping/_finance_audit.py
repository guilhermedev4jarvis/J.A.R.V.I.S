"""Auditoria proativa de gastos — anomalias vs média histórica."""
from __future__ import annotations

import csv
import re
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

_BASE = Path(__file__).resolve().parents[2]
_GASTOS = _BASE / "memory" / "gastos.csv"
_ALERT_THRESHOLD = 0.15  # 15% above weekly pace

try:
    from core.event_bus import publish as _eb_pub
except Exception:
    def _eb_pub(*_a, **_k):
        pass


def _parse_amount(raw: str) -> float:
    s = str(raw or "0").strip().replace("R$", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return abs(float(s))
    except Exception:
        return 0.0


def _load_rows() -> list[dict]:
    rows = []
    if not _GASTOS.is_file():
        return rows
    try:
        with _GASTOS.open(encoding="utf-8", errors="ignore") as f:
            sample = f.read(2048)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;")
            except Exception:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            for r in reader:
                rows.append({k.strip().lower(): v for k, v in r.items() if k})
    except Exception:
        pass
    # also try bank_statement soft
    try:
        from .bank_statement import bank_statement
        # no-op if not importable path
    except Exception:
        pass
    return rows


def _category(row: dict) -> str:
    for key in ("categoria", "category", "tipo", "type"):
        if row.get(key):
            return str(row[key]).strip().lower()
    desc = str(row.get("descricao") or row.get("description") or row.get("memo") or "").lower()
    if any(w in desc for w in ("ifood", "delivery", "rappi", "uber eats")):
        return "delivery"
    if any(w in desc for w in ("posto", "combust", "gasolina", "etanol")):
        return "combustivel"
    if any(w in desc for w in ("mercado", "super", "atacad", "carrefour", "pao de acucar")):
        return "mercado"
    if any(w in desc for w in ("cinema", "netflix", "spotify", "bar", "restaurante")):
        return "lazer"
    return "outros"


def _date(row: dict) -> Optional[datetime]:
    for key in ("data", "date", "quando"):
        raw = row.get(key)
        if not raw:
            continue
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(str(raw)[:10], fmt)
            except Exception:
                continue
    return None


def audit_spending_anomalies(threshold: float = _ALERT_THRESHOLD) -> list[dict]:
    rows = _load_rows()
    now = datetime.now()
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)
    week_sum: dict[str, float] = defaultdict(float)
    month_sum: dict[str, float] = defaultdict(float)
    for r in rows:
        amt = _parse_amount(r.get("valor") or r.get("amount") or r.get("value") or "0")
        if amt <= 0:
            continue
        cat = _category(r)
        dt = _date(r) or now
        if dt >= week_start:
            week_sum[cat] += amt
        if dt >= month_start:
            month_sum[cat] += amt

    alerts = []
    for cat, w in week_sum.items():
        # expected weekly from monthly mean (~ month/4.3)
        m = month_sum.get(cat) or 0.0
        weekly_avg = m / 4.3 if m > 0 else 0.0
        if weekly_avg <= 0:
            continue
        ratio = w / weekly_avg
        if ratio >= 1.0 + threshold:
            pct = int(min(200, ratio * 100))
            alert = {
                "category": cat,
                "week_total": round(w, 2),
                "weekly_avg": round(weekly_avg, 2),
                "pct_of_avg": pct,
                "message": f"gastos com {cat} esta semana já atingiram {pct}% da média semanal histórica",
            }
            alerts.append(alert)
            _eb_pub("finance.budget_alert", **alert)
    return alerts


def briefing_finance_snippet() -> str:
    alerts = audit_spending_anomalies()
    if not alerts:
        return ""
    parts = [a["message"] for a in alerts[:3]]
    return "Atenção: " + "; ".join(parts) + "."


def exponential_moving_average(values: list[float], alpha: float = 0.3) -> list[float]:
    if not values:
        return []
    out = [float(values[0])]
    for v in values[1:]:
        out.append(alpha * float(v) + (1 - alpha) * out[-1])
    return out


def detect_recurring_charges(min_count: int = 3, amount_tol: float = 2.0) -> list[dict]:
    """Find near-duplicate amounts/descriptions suggesting subscriptions."""
    rows = _load_rows()
    buckets: dict[str, list[float]] = {}
    for r in rows:
        desc = str(r.get("descricao") or r.get("description") or r.get("memo") or "").lower()
        desc = re.sub(r"\d+", "", desc)[:40].strip()
        amt = _parse_amount(r.get("valor") or r.get("amount") or "0")
        if not desc or amt <= 0:
            continue
        buckets.setdefault(desc, []).append(amt)
    recurring = []
    for desc, amts in buckets.items():
        if len(amts) < min_count:
            continue
        mean = sum(amts) / len(amts)
        if all(abs(a - mean) <= amount_tol for a in amts):
            recurring.append({"description": desc, "amount": round(mean, 2), "count": len(amts)})
    return recurring


def month_end_projection() -> dict:
    rows = _load_rows()
    from datetime import datetime
    now = datetime.now()
    month_total = 0.0
    for r in rows:
        dt = _date(r)
        if dt and dt.year == now.year and dt.month == now.month:
            month_total += _parse_amount(r.get("valor") or r.get("amount") or "0")
    day = max(1, now.day)
    daily = month_total / day
    days_in_month = 30
    try:
        import calendar
        days_in_month = calendar.monthrange(now.year, now.month)[1]
    except Exception:
        pass
    projected = daily * days_in_month
    return {
        "month_to_date": round(month_total, 2),
        "projected_month_end": round(projected, 2),
        "daily_pace": round(daily, 2),
        "day": day,
    }


def finance_report_markdown() -> str:
    alerts = audit_spending_anomalies()
    recurring = detect_recurring_charges()
    proj = month_end_projection()
    lines = ["# Relatório financeiro", ""]
    lines.append(f"- Acumulado no mês: **R$ {proj['month_to_date']:.2f}**")
    lines.append(f"- Projeção de fechamento: **R$ {proj['projected_month_end']:.2f}**")
    lines.append(f"- Ritmo diário: R$ {proj['daily_pace']:.2f}")
    lines.append("")
    lines.append("## Anomalias")
    if not alerts:
        lines.append("- Nenhuma anomalia relevante.")
    for a in alerts:
        lines.append(f"- {a.get('message')}")
    lines.append("")
    lines.append("## Possíveis recorrências")
    if not recurring:
        lines.append("- Nenhuma assinatura óbvia detectada.")
    for r in recurring[:10]:
        lines.append(f"- {r['description']}: R$ {r['amount']:.2f} (n={r['count']})")
    return "\n".join(lines)
