"""Action: detector_encomendas_portao — monitora entregas/pacotes na ROI do portao."""
from __future__ import annotations
from core.outcome import failed


def detector_encomendas_portao(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._detector_encomendas_portao_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("detector_encomendas_portao", f"impl error: {e}")


TOOL = {
    "name": "detector_encomendas_portao",
    "description": (
        "Monitora as cameras configuradas em camera_rois.json para detectar encomendas "
        "ou pacotes deixados no portao/entrada e dispara alerta com foto via Telegram/WhatsApp. "
        "Use para 'ativar detector de encomendas', 'verificar pacote no portao', 'parar detector de entregas'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["start", "stop", "status", "check_now"]},
            "roi_name": {"type": "STRING", "description": "Nome da ROI em camera_rois.json (padrao: portao)"},
            "dwell_seconds": {"type": "NUMBER", "description": "Segundos parado para confirmar pacote (padrao: 12)"},
        },
        "required": [],
    },
    "handler": detector_encomendas_portao,
    "tier": "core",
    "risk": "safe",
}