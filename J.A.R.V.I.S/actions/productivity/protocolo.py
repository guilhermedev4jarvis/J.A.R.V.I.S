"""Action: protocolo — 190 (socorro WhatsApp silencioso via iCSee) e demo.

Apenas protocolos 190 e demo. 190 é imediato, sem owner_gate/confirm/PIN,
sem ligação telefônica. Câmeras via app/web iCSee (+ RTSP opcional).
"""
from __future__ import annotations

from core.outcome import failed


def protocolo(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._protocolo_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("protocolo", f"impl error: {e}")


TOOL = {
    "name": "protocolo",
    "description": (
        "Ativa protocolos 190 ou demo (somente estes dois). "
        "Use para 'ativar protocolo 190' ou 'ativar protocolo demo'. "
        "190: emergência SILENCIOSA e IMEDIATA — abre iCSee, analisa câmeras da casa, "
        "envia print + socorro por WhatsApp e, se configurado, Telegram/Webhook (sem ligação, sem biometria/PIN, sem TTS no PC). Status: Protocolo 190 executado em silêncio. "
        "demo: demonstração falada com iCSee, sem mensagem de emergência. "
        "Actions: list | get | ativar."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "list | get | ativar",
                "enum": ["list", "get", "ativar"],
            },
            "nome": {
                "type": "STRING",
                "description": "190 ou demo",
            },
            "protocolo": {"type": "STRING", "description": "Alias de nome"},
        },
        "required": [],
    },
    "handler": protocolo,
    "tier": "core",
    "risk": "destructive",
}
