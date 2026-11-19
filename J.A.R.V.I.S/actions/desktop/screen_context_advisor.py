"""Action: screen_context_advisor — multimodal visual Q&A about the screen."""
from __future__ import annotations
from core.outcome import failed

def screen_context_advisor(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._screen_context_advisor_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("screen_context_advisor", f"impl error: {e}")

TOOL = {
    "name": "screen_context_advisor",
    "description": (
        "Analise visual multimodal da tela (Gemini): UI, layout, erros graficos e "
        "orientacao de onde clicar. Diferente de screenshot_ocr (so texto OCR). "
        "Use for 'o que esta errado nessa tela', 'onde clico para exportar', "
        "'explica esse grafico'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "question": {"type": "STRING", "description": "Pergunta sobre o que esta na tela"},
            "region": {"type": "STRING", "description": "full | active"},
            "image_base64": {"type": "STRING", "description": "Opcional: PNG em base64 (testes)"},
        },
        "required": [],
    },
    "handler": screen_context_advisor,
    "tier": "core",
    "risk": "review",
}
