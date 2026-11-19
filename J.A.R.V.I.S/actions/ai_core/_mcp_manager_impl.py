
"""mcp_manager — controle dos servidores MCP em config/mcp_servers.json."""
from __future__ import annotations

import json
from pathlib import Path
from core.outcome import done, ask, failed
from core.resilience import atomic_write_json, safe_read_json

_CFG = Path(__file__).resolve().parents[2] / "config" / "mcp_servers.json"


def _load():
    data = safe_read_json(_CFG, default={"servers": []})
    if not isinstance(data, dict):
        return {"servers": []}
    data.setdefault("servers", [])
    return data


def _save(data):
    atomic_write_json(_CFG, data)


def run(parameters=None, player=None, **_ctx) -> str:
    from actions.security._security_vision import speak_short
    p = dict(parameters or {})
    action = str(p.get("action") or "list").lower()
    name = str(p.get("name") or p.get("text") or "").strip()

    if action in ("list", "status"):
        try:
            from core import mcp_client
            summary = mcp_client.status_summary() if hasattr(mcp_client, "status_summary") else {"servers": _load().get("servers")}
        except Exception as e:
            summary = {"error": str(e)[:120], "servers": _load().get("servers")}
        speak_short("Status dos servidores MCP, Senhor.", player=player)
        return done("mcp_manager", action="list", **summary)

    if action == "reload":
        try:
            from core import mcp_client
            if hasattr(mcp_client, "boot_mcp_async"):
                mcp_client.boot_mcp_async(timeout=8.0)
            speak_short("Recarregando servidores MCP, Senhor.", player=player)
            return done("mcp_manager", action="reload", ok=True)
        except Exception as e:
            return failed("mcp_manager", str(e)[:160])

    if action in ("enable", "disable"):
        if not name:
            return ask("mcp_manager", "Qual servidor MCP, Senhor?")
        data = _load()
        found = False
        for s in data.get("servers") or []:
            if str(s.get("name") or "").lower() == name.lower():
                s["enabled"] = action == "enable"
                found = True
        if not found:
            return failed("mcp_manager", f"servidor '{name}' não encontrado")
        _save(data)
        speak_short(f"Servidor {name} {'ativado' if action=='enable' else 'desativado'}, Senhor.", player=player)
        return done("mcp_manager", action=action, name=name, servers=data.get("servers"))

    return done("mcp_manager", action="list", servers=_load().get("servers"))
