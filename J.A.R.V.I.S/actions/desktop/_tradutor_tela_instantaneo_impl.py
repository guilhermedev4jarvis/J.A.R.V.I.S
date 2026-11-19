"""Captura/OCR e tradução via LLM."""
from __future__ import annotations

from core.outcome import done, failed


def _capture_text() -> str:
    try:
        from actions.desktop import screenshot_ocr as soc
        for name in ("screenshot_ocr", "run", "ocr_screen", "capture_and_ocr"):
            fn = getattr(soc, name, None)
            if not callable(fn):
                continue
            try:
                res = fn(parameters={"action": "ocr"})
            except TypeError:
                try:
                    res = fn({"action": "ocr"})
                except TypeError:
                    res = fn()
            if isinstance(res, str) and res.strip():
                return res
            if isinstance(res, dict):
                return str(res.get("text") or res.get("ocr") or res)[:8000]
    except Exception:
        pass
    return ""


def _translate(text: str, target_lang: str) -> str:
    prompt = (
        f"Traduza para {target_lang}. Mantenha nomes próprios. "
        "Responda só com a tradução.\n\n" + text[:6000]
    )
    try:
        from core import llm_client
        for fn_name in ("chat", "complete", "generate", "ask_llm"):
            fn = getattr(llm_client, fn_name, None)
            if not callable(fn):
                continue
            try:
                out = fn(prompt)
            except TypeError:
                try:
                    out = fn(prompt=prompt)
                except TypeError:
                    out = fn(messages=[{"role": "user", "content": prompt}])
            if isinstance(out, str) and out.strip():
                return out.strip()
            if isinstance(out, dict):
                return str(out.get("text") or out.get("content") or out)[:8000]
    except Exception as e:
        return f"[tradução indisponível: {e}] {text[:500]}"
    return text


def run(parameters=None, **_ctx) -> str:
    params = dict(parameters or {})
    lang = str(params.get("lang") or params.get("target") or "pt-BR").strip()
    text = str(params.get("text") or "").strip() or _capture_text()
    if not text:
        return failed(
            "tradutor_tela_instantaneo",
            "Sem texto da tela. Verifique OCR ou passe text=.",
        )
    return done(
        "tradutor_tela_instantaneo",
        lang=lang,
        source_excerpt=text[:500],
        translation=_translate(text, lang)[:4000],
    )
