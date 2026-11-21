"""Detector de assinaturas recorrentes e ociosas."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from core.outcome import done


def _fetch_transactions() -> List[Dict[str, Any]]:
    try:
        from actions.finance_shopping import bank_statement as bs
        if hasattr(bs, "load_transactions"):
            res = bs.load_transactions()
            if isinstance(res, list):
                return res
    except Exception:
        pass
    return []


def run(parameters=None, player=None, session_memory=None, **ctx):
    params = parameters or {}
    min_months = int(params.get("min_months") or 2)
    txs = _fetch_transactions()

    grouped: Dict[str, List[float]] = defaultdict(list)
    for tx in txs:
        desc = str(tx.get("description") or tx.get("merchant") or "").strip().lower()
        amt = float(tx.get("amount") or 0.0)
        if desc and amt > 0:
            grouped[desc].append(amt)

    recurring = []
    annual_savings = 0.0
    for merchant, amounts in grouped.items():
        if len(amounts) >= min_months:
            avg_val = round(sum(amounts) / len(amounts), 2)
            yearly = round(avg_val * 12, 2)
            annual_savings += yearly
            recurring.append({"service": merchant, "occurrences": len(amounts), "monthly_avg": avg_val, "annual_cost": yearly})

    return done(
        "cacador_assinaturas_esquecidas",
        f"Analise concluida: {len(recurring)} cobranca(s) recorrente(s) encontrada(s).",
        {"recurring_services": recurring, "potential_annual_savings": round(annual_savings, 2)},
    )