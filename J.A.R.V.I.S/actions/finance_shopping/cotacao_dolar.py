"""
Plugin: cotacao_dolar — cotação do dólar (e outras moedas) em tempo real.

Usa a AwesomeAPI (economia.awesomeapi.com.br), gratuita e sem chave.
Padrão: USD → BRL. Dá pra pedir qualquer par (EUR, GBP, JPY, etc.).
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from typing import Any

# Pares comuns pra mensagens mais naturais
_NOMES = {
    "USD": "dólar",
    "BRL": "real",
    "EUR": "euro",
    "GBP": "libra",
    "JPY": "iene",
    "ARS": "peso argentino",
    "CAD": "dólar canadense",
    "AUD": "dólar australiano",
    "CHF": "franco suíço",
    "CNY": "yuan",
}


def _nome(code: str) -> str:
    return _NOMES.get(code.upper(), code.upper())


def _fetch(pair: str) -> dict[str, Any]:
    """Busca cotação na AwesomeAPI. pair = 'USD-BRL'."""
    url = f"https://economia.awesomeapi.com.br/json/last/{pair}"
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/1.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    # A chave vem sem o hífen: USDBRL
    key = pair.replace("-", "")
    if key not in data:
        raise ValueError(f"Par {pair} não encontrado na resposta")
    return data[key]


def run(parameters: dict, player=None, session_memory=None) -> str:
    base = (parameters.get("moeda_base") or "USD").strip().upper()
    alvo = (parameters.get("moeda_alvo") or "BRL").strip().upper()
    valor_str = (parameters.get("valor") or "").strip().replace(",", ".")

    if base == alvo:
        return f"{base} e {alvo} são a mesma moeda, senhor."

    pair = f"{base}-{alvo}"

    try:
        info = _fetch(pair)
    except Exception as e:
        # Tenta o inverso se o par direto falhar
        try:
            info = _fetch(f"{alvo}-{base}")
            # Inverte a cotação
            bid = 1.0 / float(info["bid"])
            ask = 1.0 / float(info["ask"])
            high = 1.0 / float(info["low"])   # invertido
            low = 1.0 / float(info["high"])
            pct = -float(info.get("pctChange", 0))
            when = info.get("create_date", "")
        except Exception as e2:
            return (
                f"Não consegui buscar a cotação {base}/{alvo} agora. "
                f"Erro: {e2}"
            )
    else:
        bid = float(info["bid"])       # compra
        ask = float(info["ask"])       # venda
        high = float(info["high"])
        low = float(info["low"])
        pct = float(info.get("pctChange", 0))
        when = info.get("create_date", "")

    # Formata data
    try:
        dt = datetime.strptime(when, "%Y-%m-%d %H:%M:%S")
        quando = dt.strftime("%d/%m %H:%M")
    except Exception:
        quando = when or "agora"

    seta = "▲" if pct >= 0 else "▼"
    pct_txt = f"{seta} {pct:+.2f}%"

    # Casa decimal: BRL usa 2, JPY etc. usam 0–3
    casas = 2 if alvo in ("BRL", "USD", "EUR", "GBP", "CAD", "AUD", "CHF") else 4

    linhas = [
        f"Cotação {_nome(base)} → {_nome(alvo)} ({quando}):",
        f"  Compra:  {bid:.{casas}f}",
        f"  Venda:   {ask:.{casas}f}",
        f"  Máx/Mín: {high:.{casas}f} / {low:.{casas}f}",
        f"  Variação: {pct_txt}",
    ]

    if valor_str:
        try:
            qtd = float(valor_str)
            convertido = qtd * bid
            linhas.append(
                f"  {qtd:g} {_nome(base)} ≈ {convertido:,.{casas}f} {_nome(alvo)}"
                .replace(",", "X").replace(".", ",").replace("X", ".")
            )
        except ValueError:
            linhas.append(f"  (valor '{valor_str}' inválido pra conversão)")

    texto = "\n".join(linhas)

    if player:
        try:
            player.write_log(f"JARVIS: Cotação {base}/{alvo} = {bid:.{casas}f}")
        except Exception:
            pass

    return texto

# ── Unified action contract (migrated from plugins/) ──────────────────────────

def cotacao_dolar(parameters=None, player=None, session_memory=None, **_ctx):
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
    "name": "cotacao_dolar",
    "description": ('Migrated from plugins/cotacao_dolar.py'),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "moeda_base": {
                "type": "STRING",
                "description": "Moeda de origem (ex: USD, EUR, GBP). Padrão: USD",
            },
            "moeda_alvo": {
                "type": "STRING",
                "description": "Moeda de destino (ex: BRL, EUR). Padrão: BRL",
            },
            "valor": {
                "type": "STRING",
                "description": "Opcional. Valor a converter (ex: '100'). Se vazio, só retorna a cotação unitária.",
            },
        },
        "required": [],
    },
    "handler": cotacao_dolar,
    "tier": "plugin",
    "risk": "review",
}
