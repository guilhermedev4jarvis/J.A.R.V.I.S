"""
Action: bank_statement — analisa extrato bancário (CSV, OFX, texto colado ou PDF texto).

Produz: categorias de gasto, top merchants, tendência, sugestões de economia
e ideias gerais de reserva/investimento (educativas, não recomendação formal).

Sem chave de API ainda funciona com heurísticas locais em CSV/texto.
Com Gemini disponível, a narrativa fica mais rica e em português natural.
"""
from __future__ import annotations

import csv
import io
import re
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core import outcome

# ── Category rules (substring match on description, lowercase) ───────────────
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("moradia", ("aluguel", "rent", "condominio", "condomínio", "iptu", "energia",
                 "eletricidade", "cemig", "enel", "light", "copel", "gas", "gás",
                 "comgas", "sabesp", "saneamento", "agua", "água", "internet",
                 "vivo fibra", "claro residencial", "oi fibra", "net ")),
    ("alimentacao", ("ifood", "rappi", "uber eats", "supermerc", "padaria", "mercado",
                     "assaí", "assai", "carrefour", "extra", "pão de açúcar", "pao de acucar",
                     "restaurante", "lanchonete", "mcdonald", "burger", "pizza",
                     "outback", "starbucks", "cafeteria", "açougue", "hortifruti")),
    ("transporte", ("uber", "99 app", "99pop", "cabify", "posto", "shell", "ipiranga",
                    "br combustivel", "combustivel", "combustível", "gasolina", "etanol",
                    "estacionamento", "pedagio", "pedágio", "sem parar", "conectcar",
                    "metro", "metrô", "onibus", "ônibus", "bilhete unico", "aplicativo 99")),
    ("saude", ("farmacia", "farmácia", "drogaria", "raia", "pacheco", "hospital",
               "clinica", "clínica", "laboratorio", "laboratório", "plano de saude",
               "unimed", "amil", "sulamerica", "dentista", "exame")),
    ("educacao", ("escola", "faculdade", "universidade", "curso", "udemy", "alura",
                  "coursera", "livro", "livraria", "mensalidade", "material escolar")),
    ("lazer", ("netflix", "spotify", "disney", "hbo", "prime video", "youtube premium",
               "cinema", "ingresso", "steam", "playstation", "xbox", "nintendo",
               "show", "teatro", "viagem", "hotel", "airbnb", "booking")),
    ("compras", ("amazon", "mercado livre", "magalu", "magazine luiza", "shopee",
                 "americanas", "casas bahia", "shein", "aliexpress", "shopping")),
    ("servicos", ("google", "apple.com", "microsoft", "adobe", "icloud", "dropbox",
                  "aws", "hosting", "dominio", "domínio", "contabil", "contador")),
    ("transferencias", ("pix", "ted", "doc ", "transferencia", "transferência",
                        "envio pix", "recebimento pix")),
    ("renda", ("salario", "salário", "pagamento de salario", "provento", "rendimento",
               "dividend", "estorno", "cashback", "reembolso", "devolucao", "devolução")),
]

_DATE_RE = re.compile(
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})|(\d{4}-\d{2}-\d{2})"
)
_MONEY_RE = re.compile(
    r"(?<![\w.])(-?\d{1,3}(?:[.\s]\d{3})*,\d{2}|-?\d+[.,]\d{2}|-?\d+)(?![\w.])"
)


def _log(msg: str, player=None) -> None:
    print(f"[Bank] {msg}")
    if player:
        try:
            player.write_log(f"JARVIS: {msg}")
        except Exception:
            pass


def _parse_money(raw: str) -> Optional[float]:
    s = (raw or "").strip()
    if not s:
        return None
    s = s.replace("R$", "").replace(" ", "").strip()
    # Brazilian: 1.234,56 → 1234.56
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _categorize(desc: str) -> str:
    d = (desc or "").lower()
    for cat, keys in _RULES:
        if any(k in d for k in keys):
            return cat
    return "outros"


def _parse_csv(text: str) -> list[dict[str, Any]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";" if text.count(";") > text.count(",") else ","

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return []

    fields = {f.lower().strip(): f for f in reader.fieldnames if f}
    def pick(*cands: str) -> Optional[str]:
        for c in cands:
            for k, orig in fields.items():
                if c in k:
                    return orig
        return None

    col_date = pick("data", "date", "dt", "posted")
    col_desc = pick("descr", "histórico", "historico", "memo", "lançamento",
                    "lancamento", "title", "nome", "estabelecimento", "details")
    col_val = pick("valor", "amount", "value", "quantia", "montante")
    col_deb = pick("débito", "debito", "debit", "saida", "saída")
    col_cred = pick("crédito", "credito", "credit", "entrada")

    rows: list[dict[str, Any]] = []
    for row in reader:
        desc = (row.get(col_desc) or "").strip() if col_desc else ""
        date = (row.get(col_date) or "").strip() if col_date else ""
        amount = None
        if col_val:
            amount = _parse_money(row.get(col_val) or "")
        else:
            deb = _parse_money(row.get(col_deb) or "") if col_deb else None
            cred = _parse_money(row.get(col_cred) or "") if col_cred else None
            if deb is not None and deb != 0:
                amount = -abs(deb)
            elif cred is not None:
                amount = abs(cred)
        if amount is None and not desc:
            continue
        if amount is None:
            # try any numeric cell
            for v in row.values():
                amount = _parse_money(str(v or ""))
                if amount is not None:
                    break
        if amount is None:
            continue
        if not desc:
            desc = " | ".join(str(v) for v in row.values() if v)[:80]
        rows.append({
            "date": date,
            "description": desc,
            "amount": amount,
            "category": _categorize(desc),
        })
    return rows


def _parse_ofx_like(text: str) -> list[dict[str, Any]]:
    """Minimal OFX/QFX amount+memo extraction."""
    rows: list[dict[str, Any]] = []
    blocks = re.split(r"(?=<STMTTRN>|</STMTTRN>)", text, flags=re.I)
    for b in blocks:
        if "TRNAMT" not in b.upper():
            continue
        amt_m = re.search(r"<TRNAMT>([^<\r\n]+)", b, re.I)
        memo_m = re.search(r"<(?:MEMO|NAME)>([^<\r\n]+)", b, re.I)
        date_m = re.search(r"<DTPOSTED>([^<\r\n]+)", b, re.I)
        if not amt_m:
            continue
        amount = _parse_money(amt_m.group(1))
        if amount is None:
            continue
        desc = (memo_m.group(1).strip() if memo_m else "OFX")
        date = (date_m.group(1).strip()[:8] if date_m else "")
        rows.append({
            "date": date,
            "description": desc,
            "amount": amount,
            "category": _categorize(desc),
        })
    return rows


def _parse_free_text(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        money_matches = list(_MONEY_RE.finditer(line))
        if not money_matches:
            continue
        # last money token on the line is usually the amount
        m = money_matches[-1]
        amount = _parse_money(m.group(1))
        if amount is None:
            continue
        desc = (line[: m.start()] + line[m.end():]).strip(" -\t|;")
        date_m = _DATE_RE.search(line)
        date = date_m.group(0) if date_m else ""
        # Bank statements: purchases are often positive in export but mean outflow
        # Heuristic: if description looks like expense keywords, force negative
        # when the file never used signs.
        rows.append({
            "date": date,
            "description": desc or "lançamento",
            "amount": amount,
            "category": _categorize(desc),
        })
    return rows


def _load_transactions(path: Optional[str], text: Optional[str]) -> list[dict[str, Any]]:
    content = (text or "").strip()
    if path:
        p = Path(path).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"arquivo não encontrado: {p}")
        raw = p.read_bytes()
        # try utf-8 then latin-1
        for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                content = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            content = raw.decode("utf-8", errors="replace")

        suffix = p.suffix.lower()
        if suffix in (".csv", ".txt", ".tsv"):
            rows = _parse_csv(content)
            if rows:
                return rows
        if suffix in (".ofx", ".qfx"):
            rows = _parse_ofx_like(content)
            if rows:
                return rows
        if suffix == ".pdf":
            # best-effort text extract
            extracted = _pdf_text(p)
            if extracted:
                content = extracted

    if not content:
        return []

    if "<OFX" in content.upper() or "<STMTTRN>" in content.upper():
        rows = _parse_ofx_like(content)
        if rows:
            return rows

    # Prefer CSV when it looks tabular
    if content.count("\n") >= 2 and ("," in content or ";" in content):
        rows = _parse_csv(content)
        if len(rows) >= 2:
            return rows

    return _parse_free_text(content)


def _pdf_text(path: Path) -> str:
    try:
        import pdfplumber  # type: ignore
        parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:30]:
                parts.append(page.extract_text() or "")
        return "\n".join(parts)
    except Exception:
        pass
    try:
        from PyPDF2 import PdfReader  # type: ignore
        reader = PdfReader(str(path))
        return "\n".join((pg.extract_text() or "") for pg in reader.pages[:30])
    except Exception:
        return ""


def _analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    expenses = [r for r in rows if r["amount"] < 0]
    income = [r for r in rows if r["amount"] > 0]

    # If the export has only positive numbers, treat non-renda as expenses
    if not expenses and income:
        reclass = []
        for r in rows:
            if r["category"] == "renda":
                reclass.append(r)
            else:
                reclass.append({**r, "amount": -abs(r["amount"]),
                                "category": r["category"] if r["category"] != "outros"
                                else _categorize(r["description"])})
        rows = reclass
        expenses = [r for r in rows if r["amount"] < 0]
        income = [r for r in rows if r["amount"] > 0]

    by_cat: dict[str, float] = defaultdict(float)
    by_desc: dict[str, float] = defaultdict(float)
    for r in expenses:
        by_cat[r["category"]] += abs(r["amount"])
        key = re.sub(r"\s+", " ", r["description"])[:48].strip() or "—"
        by_desc[key] += abs(r["amount"])

    total_out = sum(abs(r["amount"]) for r in expenses)
    total_in = sum(r["amount"] for r in income)
    balance = total_in - total_out

    top_cats = sorted(by_cat.items(), key=lambda x: -x[1])[:8]
    top_merchants = sorted(by_desc.items(), key=lambda x: -x[1])[:8]

    amounts = [abs(r["amount"]) for r in expenses]
    avg = statistics.mean(amounts) if amounts else 0.0
    median = statistics.median(amounts) if amounts else 0.0

    # Savings tips (rule-based)
    tips: list[str] = []
    if total_out > 0:
        for cat, val in top_cats[:3]:
            pct = 100.0 * val / total_out
            if cat == "alimentacao" and pct >= 25:
                tips.append(
                    f"Alimentação é {pct:.0f}% das saídas — vale comparar iFood/delivery "
                    "com mercado e definir um teto semanal."
                )
            elif cat == "lazer" and pct >= 15:
                tips.append(
                    f"Lazer/streaming consome {pct:.0f}% — revise assinaturas que você "
                    "quase não usa e compartilhe planos familiares quando fizer sentido."
                )
            elif cat == "transporte" and pct >= 15:
                tips.append(
                    f"Transporte é {pct:.0f}% — apps de corrida + combustível somam rápido; "
                    "agrupar trajetos e transporte público nos picos ajuda."
                )
            elif cat == "compras" and pct >= 15:
                tips.append(
                    f"Compras online são {pct:.0f}% — espere 48h antes de checkout e "
                    "evite parcelar o que não é essencial."
                )
            elif cat == "outros" and pct >= 30:
                tips.append(
                    "Muitos gastos caíram em 'outros' — renomear/categorizar no app do "
                    "banco melhora o próximo relatório."
                )
    if total_in > 0 and balance < 0:
        tips.append(
            "Saídas superaram entradas neste recorte — priorize cortar as 3 categorias "
            "mais altas antes de qualquer investimento novo."
        )
    if total_in > 0 and balance / max(total_in, 1) >= 0.2:
        tips.append(
            "Sobrou cerca de 20%+ da receita neste período — candidato a reserva de "
            "emergência antes de risco maior."
        )
    if not tips:
        tips.append(
            "Mantenha um registro mensal fixo; o ganho maior costuma ser enxergar "
            "vazamentos pequenos e recorrentes."
        )

    # Educational investment guidance (not personalized financial advice)
    invest: list[str] = []
    if balance <= 0:
        invest.append(
            "Com saldo negativo no período, o passo zero é estancar o déficit e montar "
            "uma reserva mínima (ex.: 1–3 meses de custos essenciais) em aplicação líquida."
        )
    else:
        invest.append(
            "Ordem clássica: (1) reserva de emergência em liquidez diária, "
            "(2) quitar juros altos de cartão/cheque especial, "
            "(3) só então investir o excedente com horizonte definido."
        )
        invest.append(
            "Para horizontes curtos (<2 anos), priorize baixo risco e liquidez. "
            "Para longos prazos, diversificação ampla costuma superar 'dicas quentes'."
        )
        invest.append(
            "Isto é educação financeira geral, não recomendação de produto, "
            "papel ou corretora."
        )

    return {
        "transactions": len(rows),
        "expenses_count": len(expenses),
        "income_count": len(income),
        "total_out": round(total_out, 2),
        "total_in": round(total_in, 2),
        "balance": round(balance, 2),
        "avg_expense": round(avg, 2),
        "median_expense": round(median, 2),
        "top_categories": top_cats,
        "top_merchants": top_merchants,
        "tips": tips,
        "invest": invest,
    }


def _fmt_money(v: float) -> str:
    sign = "-" if v < 0 else ""
    return f"{sign}R$ {abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _report(analysis: dict[str, Any]) -> str:
    lines = [
        f"Transações: {analysis['transactions']} "
        f"(saídas {analysis['expenses_count']}, entradas {analysis['income_count']})",
        f"Total saídas: {_fmt_money(analysis['total_out'])}",
        f"Total entradas: {_fmt_money(analysis['total_in'])}",
        f"Saldo do período: {_fmt_money(analysis['balance'])}",
        f"Ticket médio saída: {_fmt_money(analysis['avg_expense'])} "
        f"(mediana {_fmt_money(analysis['median_expense'])})",
        "",
        "Top categorias de gasto:",
    ]
    for cat, val in analysis["top_categories"]:
        pct = (100 * val / analysis["total_out"]) if analysis["total_out"] else 0
        lines.append(f"  • {cat}: {_fmt_money(val)} ({pct:.0f}%)")
    lines.append("")
    lines.append("Maiores lançamentos (agrupados):")
    for desc, val in analysis["top_merchants"][:5]:
        lines.append(f"  • {desc}: {_fmt_money(val)}")
    lines.append("")
    lines.append("Para economizar:")
    for t in analysis["tips"]:
        lines.append(f"  • {t}")
    lines.append("")
    lines.append("Reserva / investir (educativo):")
    for t in analysis["invest"]:
        lines.append(f"  • {t}")
    return "\n".join(lines)


def _gemini_polish(report: str, analysis: dict[str, Any]) -> Optional[str]:
    try:
        from core import gemini
        key_path = Path(__file__).resolve().parents[2] / "config" / "api_keys.json"
        import json
        key = ""
        try:
            key = json.loads(key_path.read_text(encoding="utf-8")).get("gemini_api_key") or ""
        except Exception:
            key = ""
        if not key:
            return None
        prompt = (
            "Você é um assistente financeiro prudente. Com base no relatório abaixo, "
            "escreva em português do Brasil um resumo claro (máx. 12 frases) sobre "
            "para onde o dinheiro foi, 3 cortes práticos de gasto e 2 orientações "
            "educativas sobre reserva/investimento. "
            "NÃO recomende tickers, criptomoedas específicas nem diga 'invista em X'. "
            "Deixe explícito que não é recomendação de investimento formal.\n\n"
            f"{report}\n"
        )
        text = gemini.text(prompt, tier=getattr(gemini, "SMART", "SMART"), timeout_ms=60_000)
        return (text or "").strip() or None
    except Exception as e:
        _log(f"Gemini polish skipped: {e}")
        return None


def bank_statement(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    path = (params.get("path") or params.get("file") or "").strip() or None
    text = (params.get("text") or params.get("content") or params.get("extract") or "")
    text = text.strip() if isinstance(text, str) else ""

    if not path and not text:
        return outcome.ask(
            "bank_statement",
            "Envie o caminho do extrato (CSV/OFX/PDF texto) ou cole o texto/CSV do período.",
        )

    try:
        rows = _load_transactions(path, text)
    except FileNotFoundError as e:
        return outcome.failed("bank_statement", str(e))
    except Exception as e:
        return outcome.failed("bank_statement", f"falha ao ler extrato: {e}")

    if len(rows) < 2:
        return outcome.failed(
            "bank_statement",
            "não encontrei lançamentos suficientes — use CSV com colunas data/"
            "descrição/valor, OFX, ou cole várias linhas com valores",
            path=path or "",
        )

    analysis = _analyze(rows)
    report = _report(analysis)
    polished = _gemini_polish(report, analysis)
    final = polished or report

    _log(f"Analyzed {analysis['transactions']} rows; out={analysis['total_out']}", player)

    # Keep model-facing payload compact but structured
    top_cat_str = ", ".join(f"{c}={v:.2f}" for c, v in analysis["top_categories"][:5])
    return outcome.done(
        "bank_statement",
        transactions=analysis["transactions"],
        total_out=analysis["total_out"],
        total_in=analysis["total_in"],
        balance=analysis["balance"],
        top_categories=top_cat_str,
        report=final[:4000],
    )


TOOL = {
    "name": "bank_statement",
    "description": (
        "Analisa extrato bancário (arquivo CSV/OFX/PDF ou texto colado): total de "
        "entradas e saídas, categorias de gasto, maiores lançamentos, dicas práticas "
        "de economia e orientações educativas sobre reserva/investimento. "
        "Use quando o usuário enviar extrato, perguntar para onde vai o dinheiro, "
        "como economizar ou o que fazer com o que sobra. "
        "Não é aconselhamento financeiro formal."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {
                "type": "STRING",
                "description": "Caminho local do extrato (.csv, .ofx, .txt, .pdf).",
            },
            "text": {
                "type": "STRING",
                "description": "Conteúdo colado do extrato quando não houver arquivo.",
            },
        },
        "required": [],
    },
    "handler": bank_statement,
}
