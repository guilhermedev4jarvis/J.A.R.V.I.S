"""screen_context_advisor — multimodal Gemini analysis of the current screen."""
from __future__ import annotations

import base64
import io
from typing import Optional

from core.outcome import ask, done, failed, unverified


def _redact_text(text: str) -> str:
    try:
        from core.redaction import redact_text
        return redact_text(text or "")
    except Exception:
        return text or ""


def _capture_png(region: str = "full") -> bytes:
    region = (region or "full").lower()
    try:
        import mss
        import mss.tools
        with mss.mss() as sct:
            mon = sct.monitors[1]
            shot = sct.grab(mon)
            return mss.tools.to_png(shot.rgb, shot.size)
    except Exception:
        pass
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        raise RuntimeError(f"screen capture unavailable: {e}") from e


def _downscale(png: bytes, max_side: int = 1280) -> bytes:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(png))
        w, h = img.size
        scale = min(1.0, max_side / max(w, h))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)))
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:
        return png


def _gemini_vision(question: str, png: bytes) -> str:
    """Call Gemini multimodal; raises on hard failure, returns text on success."""
    from core import gemini as gem
    from google.genai import types as gtypes

    key = gem.api_key()
    if not key:
        raise RuntimeError("offline: no Gemini API key")

    png = _downscale(png)
    part = gtypes.Part.from_bytes(data=png, mime_type="image/png")
    prompt = (
        "You are J.A.R.V.I.S. (MARK LXI), a desktop visual advisor. "
        "Analyze the screenshot and answer in the user's language. "
        "Be specific about UI elements, errors, and step-by-step clicks when relevant. "
        "Do not invent buttons that are not visible.\n\n"
        f"User question: {question}"
    )
    # Prefer SMART tier for vision reasoning
    reply = gem.text([prompt, part], tier=getattr(gem, "SMART", "smart"), timeout_ms=90_000, key=key)
    if not reply:
        # fallback FAST
        reply = gem.text([prompt, part], tier=getattr(gem, "FAST", "fast"), timeout_ms=60_000, key=key)
    if not reply:
        raise RuntimeError("Gemini returned empty vision reply")
    return _redact_text(reply)


def run(parameters: Optional[dict] = None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    question = str(
        p.get("question") or p.get("query") or p.get("prompt") or p.get("text") or ""
    ).strip()
    if not question:
        return ask("screen_context_advisor", "O que você quer saber sobre a tela?")

    region = str(p.get("region") or p.get("mode") or "full").strip().lower()
    # allow injected image for tests
    img_b64 = p.get("image_base64")
    try:
        if img_b64:
            png = base64.b64decode(img_b64)
        else:
            png = _capture_png(region)
    except Exception as e:
        return failed("screen_context_advisor", f"captura falhou: {e}")

    try:
        answer = _gemini_vision(question, png)
        return done(
            "screen_context_advisor",
            op="advise",
            question=question[:200],
            answer=answer[:4000],
            bytes=len(png),
        )
    except Exception as e:
        msg = str(e)
        if "offline" in msg.lower() or "no Gemini" in msg or "API key" in msg:
            return unverified(
                "screen_context_advisor",
                "visão multimodal indisponível (offline/sem chave); tente screenshot_ocr para texto",
                question=question[:200],
            )
        return failed("screen_context_advisor", f"análise visual falhou: {msg[:200]}")
