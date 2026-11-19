"""Action: offline — interruptor central de rede e processamento local."""
from __future__ import annotations
from core.outcome import failed

def offline(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._offline_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("offline", f"impl error: {e}")

TOOL = {
    "name": "offline",
    "description": (
        "Ativa/desativa modo offline (bunker): bloqueia APIs externas e força Ollama+Whisper+Piper. "
        "Gatilhos: 'ativar modo offline', 'desativar internet', 'modo bunker', /offline; "
        "'voltar online', /online; 'preparar sistema offline', /preparar_offline."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["enable", "disable", "status", "prepare", "online", "offline"],
            },
        },
        "required": [],
    },
    "handler": offline,
    "tier": "core",
    "risk": "safe",
}
