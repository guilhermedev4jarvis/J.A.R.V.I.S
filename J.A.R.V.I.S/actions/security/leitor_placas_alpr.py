"""Action: leitor_placas_alpr."""
from __future__ import annotations
from core.outcome import failed

def leitor_placas_alpr(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._leitor_placas_alpr_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("leitor_placas_alpr", f"impl error: {e}")

TOOL = {
    "name": "leitor_placas_alpr",
    "description": ("Lê placa/modelo/cor no portão (iCSee Câmera 2) e compara com memory/veiculos_conhecidos.json. "
    "Gatilhos: ler placa no portão, que carro está lá fora, cadastrar placa, /placa."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["read", "register", "list"]},
            "text": {"type": "STRING"},
            "name": {"type": "STRING"},
            "plate": {"type": "STRING"},
            "query": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": leitor_placas_alpr,
    "tier": "core",
    "risk": "safe",
}
