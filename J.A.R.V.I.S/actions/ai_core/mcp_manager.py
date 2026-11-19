"""Action: mcp_manager — listar/recarregar/ativar servidores MCP."""
from __future__ import annotations
from core.outcome import failed

def mcp_manager(parameters=None, player=None, session_memory=None, **ctx):
    try:
        from ._mcp_manager_impl import run
        return run(parameters, player=player, session_memory=session_memory, **ctx)
    except Exception as e:
        return failed("mcp_manager", f"impl error: {e}")

TOOL = {
    "name": "mcp_manager",
    "description": (
        "Gerencia servidores MCP: listar, recarregar, ativar/desativar por nome. "
        "Gatilhos: 'listar servidores MCP', 'recarregar servidores MCP', 'ativar servidor MCP [nome]', /mcp."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["list", "reload", "enable", "disable", "status"]},
            "name": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": mcp_manager,
    "tier": "core",
    "risk": "review",
}
