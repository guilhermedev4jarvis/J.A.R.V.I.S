"""Action: scanner_nota_fiscal_qr — le QR Code/URL de NFC-e e registra gastos e precos."""
from __future__ import annotations
from core.outcome import failed


def scanner_nota_fiscal_qr(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._scanner_nota_fiscal_qr_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("scanner_nota_fiscal_qr", f"impl error: {e}")


TOOL = {
    "name": "scanner_nota_fiscal_qr",
    "description": (
        "Extrai dados de QR Code ou URL de NFC-e, registra a compra no controle de gastos "
        "e atualiza o historico de precos por produto. "
        "Use para 'escanear nota fiscal', 'registrar cupom fiscal por qr code'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "nfce_url": {"type": "STRING", "description": "URL extraida do QR Code da NFC-e"},
            "image_path": {"type": "STRING", "description": "Caminho opcional de imagem com QR Code"},
            "store": {"type": "STRING", "description": "Nome do estabelecimento"},
            "total_amount": {"type": "NUMBER", "description": "Valor total da nota (se informado)"},
        },
        "required": [],
    },
    "handler": scanner_nota_fiscal_qr,
    "tier": "core",
    "risk": "safe",
}