"""Action: sintetizador_voz_clonada — gerencia perfis prosodicos dinamicos de voz TTS."""
from __future__ import annotations
from core.outcome import failed


def sintetizador_voz_clonada(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._sintetizador_voz_clonada_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("sintetizador_voz_clonada", f"impl error: {e}")


TOOL = {
    "name": "sintetizador_voz_clonada",
    "description": (
        "Ajusta o perfil prosodico de voz (velocidade, tom e enfase) conforme o contexto "
        "(alerta_critico, briefing_matinal, tutor_calmo, modo_noturno_sussurro) e fala o texto. "
        "Use para 'mudar tom de voz para alerta', 'ativar voz modo noturno', 'falar com tom calmo'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["set_profile", "speak", "status"]},
            "profile": {
                "type": "STRING",
                "enum": ["padrao", "alerta_critico", "briefing_matinal", "tutor_calmo", "modo_noturno_sussurro"],
            },
            "text": {"type": "STRING", "description": "Texto opcional para sintetizar imediatamente"},
        },
        "required": [],
    },
    "handler": sintetizador_voz_clonada,
    "tier": "core",
    "risk": "safe",
}