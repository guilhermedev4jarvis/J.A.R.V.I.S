
"""escritorio_documentos — DOCX/PDF via LLM outline."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from core.outcome import done, ask, failed
from actions.security._security_vision import send_telegram, speak_short

_DIR = Path(__file__).resolve().parents[2] / "memory" / "documentos_gerados"

def _content(kind: str, details: str) -> str:
    try:
        from core.llm_client import call_llm_text
        return (call_llm_text(
            f"Redija em português um {kind} profissional com base em: {details}. Texto completo, seções claras.",
            system="Documento formal, objetivo.",
            timeout=60,
        ) or details).strip()
    except Exception:
        return f"{kind.upper()}\n\n{details}\n\nDocumento gerado pelo J.A.R.V.I.S. em {datetime.now().isoformat()}."

def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    details = str(p.get("details") or p.get("text") or p.get("query") or p.get("topic") or "").strip()
    kind = str(p.get("name") or "documento").strip() or "documento"
    if not details:
        return ask("escritorio_documentos", "Descreva o documento desejado, Senhor.")
    body = _content(kind, details)
    _DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    docx_path = _DIR / f"{kind}_{stamp}.docx"
    pdf_path = _DIR / f"{kind}_{stamp}.pdf"
    files = []
    try:
        from docx import Document
        doc = Document()
        doc.add_heading(kind.title(), level=1)
        for para in body.split("\n"):
            if para.strip():
                doc.add_paragraph(para.strip())
        doc.save(str(docx_path))
        files.append(str(docx_path))
    except Exception as e:
        docx_path = None
    try:
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(True, 15)
        pdf.set_font("Helvetica", size=11)
        for line in body.split("\n"):
            pdf.multi_cell(0, 6, line[:200])
        pdf.output(str(pdf_path))
        files.append(str(pdf_path))
    except Exception:
        # plaintext fallback
        txt = _DIR / f"{kind}_{stamp}.txt"
        txt.write_text(body, encoding="utf-8")
        files.append(str(txt))
        pdf_path = txt
    # send one file
    send_path = str(pdf_path if pdf_path and Path(str(pdf_path)).exists() else files[0])
    try:
        import requests, os
        token, chat = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
        if token and chat and Path(send_path).is_file():
            with open(send_path, "rb") as fh:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data={"chat_id": chat, "caption": f"Documento: {kind}"},
                    files={"document": fh},
                    timeout=60,
                )
    except Exception:
        pass
    speak_short("Documento gerado, Senhor.", player=player)
    return done("escritorio_documentos", action="generate", kind=kind, files=files)
