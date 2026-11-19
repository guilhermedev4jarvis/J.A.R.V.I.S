"""Minimal MCP-like JSON-RPC 2.0 over stdio for local JARVIS servers."""
from __future__ import annotations

import json
import sys
from typing import Any, Callable


def serve(tools: dict[str, dict], handlers: dict[str, Callable[[dict], Any]]) -> None:
    """tools: name -> {description, inputSchema}; handlers: name -> fn(args)->result."""

    def reply(msg_id: Any, result: Any = None, error: Any = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id}
        if error is not None:
            payload["error"] = error
        else:
            payload["result"] = result
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        msg_id = req.get("id")
        method = req.get("method") or ""
        params = req.get("params") or {}
        try:
            if method in ("initialize", "notifications/initialized"):
                if method == "initialize":
                    reply(
                        msg_id,
                        {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "jarvis-local-mcp", "version": "1.0"},
                        },
                    )
                continue
            if method == "tools/list":
                listing = []
                for name, meta in tools.items():
                    listing.append(
                        {
                            "name": name,
                            "description": meta.get("description") or name,
                            "inputSchema": meta.get("inputSchema")
                            or {"type": "object", "properties": {}},
                        }
                    )
                reply(msg_id, {"tools": listing})
                continue
            if method == "tools/call":
                name = (params.get("name") if isinstance(params, dict) else None) or ""
                args = (params.get("arguments") if isinstance(params, dict) else {}) or {}
                if name not in handlers:
                    reply(msg_id, error={"code": -32601, "message": f"Unknown tool: {name}"})
                    continue
                result = handlers[name](args if isinstance(args, dict) else {})
                # MCP content form
                text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                reply(msg_id, {"content": [{"type": "text", "text": text}]})
                continue
            if msg_id is not None:
                reply(msg_id, error={"code": -32601, "message": f"Method not found: {method}"})
        except Exception as e:
            if msg_id is not None:
                reply(msg_id, error={"code": -32000, "message": str(e)[:300]})
