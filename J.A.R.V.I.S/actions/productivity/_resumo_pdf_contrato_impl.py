"""Extrai texto de PDF e resume cláusulas."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.outcome import ask, done, failed


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:40])
    except Exception:
        pass
    try:
        import PyPDF2
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return "\n".join((p.extract_text() or "") for p in reader.pages[:40])
    except Exception:
        pass
    try:
        import fitz
        doc = fitz.open(str(path))
        return "\n".join((doc.load_page(i).get_text() or "") for i in range(min(40, doc.page_count)))
    except Exception:
        pass
    return ""


def _heuristic_summary(text: str) -> dict[str, Any]:
    money = re.findall(r"(?:R\$\s*)?\d{1,3}(?:\.\d{3})*,\d{2}", text)
    dates = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text)
    multa = [ln.strip() for ln in text.splitlines() if "multa" in ln.lower()][:5]
    cancel = [ln.strip() for ln in text.splitlines() if "cancel" in ln.lower() or "rescis" in ln.lower()][:5]
    return {
        "valores": money[:10],
        "datas": dates[:10],
        "clausulas_multa": multa,
        "clausulas_cancelamento": cancel,
        "excerpt": text[:800],
    }


def _llm_summary(text: str) -> str:
    prompt = (
        "Resuma o documento: partes, valores, datas, multas/cancelamento e pontos de atenção.\n"
        + text[:8000]
    )
    try:
        from core import llm_client
        for name in ("chat", "complete", "generate"):
            fn = getattr(llm_client, name, None)
            if not callable(fn):
                continue
            try:
                out = fn(prompt)
            except TypeError:
                out = fn(prompt=prompt)
            if isinstance(out, str):
                return out[:4000]
    except Exception:
        pass
    return ""


def run(parameters=None, **_ctx) -> str:
    params = dict(parameters or {})
    path_s = str(params.get("path") or params.get("file") or params.get("pdf") or "").strip()
    if not path_s:
        return ask("resumo_pdf_contrato", "Informe o caminho do PDF (path=...).")
    path = Path(path_s).expanduser()
    if not path.is_file():
        return failed("resumo_pdf_contrato", f"arquivo não encontrado: {path}")
    text = _extract_pdf(path)
    if not text.strip():
        return failed("resumo_pdf_contrato", "Falha ao extrair texto. Instale pypdf ou pymupdf.")
    structured = _heuristic_summary(text)
    llm = _llm_summary(text)
    return done("resumo_pdf_contrato", path=str(path), summary=llm or structured, structured=structured)
