"""Action pública: perfis de layout de janelas."""
from __future__ import annotations

from core.outcome import failed
from ._organizador_janelas_perfil_impl import run as _run


def organizador_janelas_perfil(parameters=None, **ctx) -> str:
    try:
        return _run(parameters, **ctx)
    except Exception as e:
        return failed("organizador_janelas_perfil", str(e)[:240])


TOOL = {
    "name": "organizador_janelas_perfil",
    "description": (
        "Salva/restaura layouts de janelas em config/window_workspaces.json. "
        "action=salvar_perfil|aplicar_perfil|listar_perfis."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING"},
            "mode": {"type": "STRING"},
            "name": {"type": "STRING"},
            "profile": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": organizador_janelas_perfil,
    "tier": "core",
    "risk": "safe",
}
