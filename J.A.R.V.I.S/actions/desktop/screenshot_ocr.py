"""
Action: screenshot_ocr — captura a tela (ou lê uma imagem) e extrai texto (OCR).

Ordem de engines:
  1. pytesseract (local, se instalado)
  2. Gemini vision (se houver API key)
  3. mensagem clara pedindo dependência

Também aceita path de imagem já existente para não forçar novo print.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Optional

from core import outcome
from core.lazyimport import installed

_HAS_MSS = installed("mss")
_HAS_PIL = installed("PIL")
_HAS_TESS = installed("pytesseract")


def _log(msg: str, player=None) -> None:
    print(f"[OCR] {msg}")
    if player:
        try:
            player.write_log(f"JARVIS: {msg}")
        except Exception:
            pass


def _config_key() -> str:
    cfg_path = Path(__file__).resolve().parents[2] / "config" / "api_keys.json"
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8")).get("gemini_api_key") or ""
    except Exception:
        return ""


def _capture_png() -> bytes:
    if not _HAS_MSS:
        raise RuntimeError(
            "mss não está instalado — rode: pip install mss"
        )
    import mss
    import mss.tools

    with mss.mss() as sct:
        monitors = sct.monitors
        target = monitors[1] if len(monitors) > 1 else monitors[0]
        shot = sct.grab(target)
        return mss.tools.to_png(shot.rgb, shot.size)


def _load_image_bytes(path: str) -> bytes:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"imagem não encontrada: {p}")
    return p.read_bytes()


def _ocr_tesseract(img_bytes: bytes, lang: str) -> Optional[str]:
    if not _HAS_TESS or not _HAS_PIL:
        return None
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(img_bytes))
        # Prefer Portuguese+English when available
        langs = lang or "por+eng"
        try:
            text = pytesseract.image_to_string(img, lang=langs)
        except Exception:
            text = pytesseract.image_to_string(img, lang="eng")
        text = (text or "").strip()
        return text or None
    except Exception as e:
        _log(f"tesseract failed: {e}")
        return None


def _ocr_gemini(img_bytes: bytes, mime: str = "image/png") -> Optional[str]:
    key = _config_key()
    if not key:
        return None
    try:
        from core import gemini
        from google.genai import types

        prompt = (
            "Extract ALL readable text from this screenshot. "
            "Preserve reading order. Return plain text only — no markdown, "
            "no commentary. If there is no text, return exactly: (no text)"
        )
        # Prefer a compact call: text + inline image when the ladder supports it
        part_text = prompt
        try:
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(part_text),
                        types.Part.from_bytes(data=img_bytes, mime_type=mime),
                    ],
                )
            ]
        except Exception:
            # Older SDK shape
            contents = [prompt, {"mime_type": mime, "data": img_bytes}]

        text = gemini.text(contents, tier=getattr(gemini, "SMART", "SMART"), timeout_ms=60_000)
        text = (text or "").strip()
        if not text or text.lower() in ("(no text)", "no text"):
            return None
        return text
    except Exception as e:
        _log(f"gemini OCR failed: {e}")
        return None


def _clean(text: str, max_len: int = 6000) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_len:
        text = text[:max_len] + "\n…"
    return text


def screenshot_ocr(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    path = (params.get("path") or params.get("image") or "").strip()
    lang = (params.get("lang") or "por+eng").strip()
    region = (params.get("region") or "full").strip().lower()

    try:
        if path:
            img_bytes = _load_image_bytes(path)
            source = f"file:{path}"
            mime = "image/png"
            low = path.lower()
            if low.endswith((".jpg", ".jpeg")):
                mime = "image/jpeg"
            elif low.endswith(".webp"):
                mime = "image/webp"
        else:
            img_bytes = _capture_png()
            source = "screen"
            mime = "image/png"
            # region reserved for future crop; full screen for now
            if region not in ("full", "screen", ""):
                _log(f"region '{region}' not implemented yet — using full screen", player)
    except FileNotFoundError as e:
        return outcome.failed("screenshot_ocr", str(e))
    except RuntimeError as e:
        return outcome.failed("screenshot_ocr", str(e))
    except Exception as e:
        return outcome.failed("screenshot_ocr", f"falha ao capturar/ler imagem: {e}")

    text = _ocr_tesseract(img_bytes, lang)
    engine = "tesseract" if text else None

    if not text:
        text = _ocr_gemini(img_bytes, mime=mime)
        engine = "gemini" if text else None

    if not text:
        return outcome.failed(
            "screenshot_ocr",
            "não consegui extrair texto. Instale OCR local "
            "(`pip install pytesseract pillow` + Tesseract OCR no sistema) "
            "ou configure a chave Gemini em config/api_keys.json",
            source=source,
        )

    cleaned = _clean(text)
    preview = cleaned if len(cleaned) <= 500 else cleaned[:500] + "…"
    _log(f"{engine} extracted {len(cleaned)} chars from {source}", player)

    return outcome.done(
        "screenshot_ocr",
        source=source,
        engine=engine,
        chars=len(cleaned),
        text=cleaned,
        preview=preview,
    )


TOOL = {
    "name": "screenshot_ocr",
    "description": (
        "Captures the screen (or reads an image file) and extracts readable text "
        "with OCR. Use when the user asks what is written on the screen, wants "
        "text from a screenshot, error dialogs, code on screen, or an image path. "
        "Works offline with Tesseract, or with Gemini vision when a key is set."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {
                "type": "STRING",
                "description": "Optional image path. If omitted, captures the screen now.",
            },
            "lang": {
                "type": "STRING",
                "description": "Tesseract languages, default 'por+eng'.",
            },
            "region": {
                "type": "STRING",
                "description": "Reserved: 'full' (default). Future: active window.",
            },
        },
        "required": [],
    },
    "handler": screenshot_ocr,
}
