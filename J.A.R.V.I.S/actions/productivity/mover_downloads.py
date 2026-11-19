"""Action: mover_downloads — recorta arquivo de Downloads para a raiz/subpastas do J.A.R.V.I.S."""
from __future__ import annotations

from core.outcome import failed


def mover_downloads(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._mover_downloads_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("mover_downloads", f"impl error: {e}")


TOOL = {
    "name": "mover_downloads",
    "description": "Recorta/move UM arquivo da pasta Downloads para destino. USE quando o usuario nomear o arquivo. NAO USE para organizacao em massa (file_organize).",
    
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["move", "open_downloads", "status"],
            },
            "filename": {"type": "STRING", "description": "Nome ou parte do nome do arquivo"},
            "destination": {
                "type": "STRING",
                "description": "root|actions|core|config|memory|desktop|documentos|caminho",
            },
            "text": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": mover_downloads,
    "tier": "core",
    "risk": "review",
}
