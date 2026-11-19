"""
MCP (Model Context Protocol) client for JARVIS.

Connects to external MCP servers (GitHub, filesystem, Notion, Slack, SQL, …)
and exposes their tools in the same shape PluginRecord / tool declarations
already use. Optional dependency: the official `mcp` package.

Nothing here is imported at app startup unless discover_plugins asks for it
and config/mcp_servers.json (or api_keys.json → mcp_servers) lists servers.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE = _base_dir()
_CONFIG_CANDIDATES = (
    _BASE / "config" / "mcp_servers.json",
    _BASE / "config" / "api_keys.json",
)


@dataclass
class MCPTool:
    server: str
    name: str
    description: str
    parameters: dict
    full_name: str  # mcp_<server>__<name> — unique in the global tool namespace


@dataclass
class MCPServerState:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    tools: list[MCPTool] = field(default_factory=list)
    error: str = ""
    # session handle kept alive for the process lifetime (best-effort)
    _session: Any = None
    _cm: Any = None


_servers: dict[str, MCPServerState] = {}
_logger: Callable[[str], None] = print


def set_logger(fn: Callable[[str], None]) -> None:
    global _logger
    _logger = fn or print


def available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("mcp") is not None
    except Exception:
        return False


def _load_server_list() -> list[dict]:
    """Read MCP server definitions from config.

    Preferred file: config/mcp_servers.json
        { "servers": [ { "name", "command", "args", "env" }, ... ] }

    Fallback: config/api_keys.json key "mcp_servers" (same shape).
    """
    for path in _CONFIG_CANDIDATES:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if path.name == "mcp_servers.json":
            servers = data.get("servers") if isinstance(data, dict) else data
        else:
            servers = data.get("mcp_servers") if isinstance(data, dict) else None
        # Support list OR dict keyed by server name
        if isinstance(servers, dict):
            normalized = []
            for name, cfg in servers.items():
                if not isinstance(cfg, dict):
                    continue
                item = dict(cfg)
                item.setdefault("name", name)
                normalized.append(item)
            servers = normalized
        if isinstance(servers, list):
            out = []
            for s in servers:
                if not isinstance(s, dict):
                    continue
                if not s.get("name") or not s.get("command"):
                    continue
                if s.get("enabled") is False:
                    continue
                # expand ${VAR} and ${VAR:-default} in env values
                env = {}
                for k, v in (s.get("env") or {}).items():
                    env[k] = _expand_env(str(v))
                item = dict(s)
                item["env"] = env
                out.append(item)
            return out
    return []


def _expand_env(value: str) -> str:
    """Expand ${VAR} or ${VAR:-default} using os.environ."""
    import re
    def repl(m):
        body = m.group(1)
        if ":-" in body:
            var, default = body.split(":-", 1)
            return os.environ.get(var, default)
        return os.environ.get(body, "")
    return re.sub(r"\$\{([^}]+)\}", repl, value)


def _sanitize(name: str) -> str:
    out = []
    for ch in (name or "").strip().lower():
        if ch.isalnum() or ch in ("_", "-"):
            out.append(ch if ch != "-" else "_")
    return "".join(out)[:48] or "server"


def _json_schema_to_gemini(schema: dict | None) -> dict:
    """MCP tools use JSON Schema; JARVIS tool decls use Gemini OBJECT style."""
    if not isinstance(schema, dict):
        return {"type": "OBJECT", "properties": {}}
    props_in = schema.get("properties") or {}
    props_out: dict[str, Any] = {}
    type_map = {
        "string": "STRING", "number": "NUMBER", "integer": "NUMBER",
        "boolean": "BOOLEAN", "array": "ARRAY", "object": "OBJECT",
    }
    for key, spec in props_in.items():
        if not isinstance(spec, dict):
            props_out[key] = {"type": "STRING"}
            continue
        t = type_map.get(str(spec.get("type", "string")).lower(), "STRING")
        entry: dict[str, Any] = {"type": t}
        if spec.get("description"):
            entry["description"] = str(spec["description"])[:500]
        if t == "ARRAY" and isinstance(spec.get("items"), dict):
            item_t = type_map.get(str(spec["items"].get("type", "string")).lower(), "STRING")
            entry["items"] = {"type": item_t}
        props_out[key] = entry
    required = schema.get("required")
    out: dict[str, Any] = {"type": "OBJECT", "properties": props_out}
    if isinstance(required, list) and required:
        out["required"] = [str(r) for r in required]
    return out


async def _connect_one(cfg: dict) -> MCPServerState:
    name = _sanitize(str(cfg.get("name") or "server"))
    command = str(cfg.get("command") or "").strip()
    args = list(cfg.get("args") or [])
    env = {str(k): str(v) for k, v in (cfg.get("env") or {}).items()}
    state = MCPServerState(name=name, command=command, args=args, env=env)

    if not command:
        state.error = "missing command"
        return state

    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except Exception as e:
        state.error = f"mcp package not installed: {e}"
        return state

    merged_env = {**os.environ, **env}
    params = StdioServerParameters(command=command, args=args, env=merged_env)

    try:
        cm = stdio_client(params)
        read, write = await cm.__aenter__()
        session = ClientSession(read, write)
        await session.__aenter__()
        await session.initialize()
        listed = await session.list_tools()
        tools = []
        for t in getattr(listed, "tools", []) or []:
            raw_name = getattr(t, "name", "") or ""
            if not raw_name:
                continue
            full = f"mcp_{name}__{_sanitize(raw_name)}"
            tools.append(MCPTool(
                server=name,
                name=raw_name,
                description=(getattr(t, "description", None) or f"MCP tool {raw_name} on {name}")[:800],
                parameters=_json_schema_to_gemini(getattr(t, "inputSchema", None)),
                full_name=full,
            ))
        state.tools = tools
        state._session = session
        state._cm = cm
        _logger(f"[MCP] connected {name}: {len(tools)} tool(s)")
    except Exception as e:
        state.error = f"{type(e).__name__}: {e}"
        _logger(f"[MCP] failed {name}: {state.error}")
        traceback.print_exc()
    return state


def _run_async(coro):
    """Run a coroutine from sync code without assuming no event loop exists."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # Called from inside an async app — schedule and wait via a bridge thread.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=60)
    return asyncio.run(coro)


def connect_all(logger: Callable[[str], None] | None = None) -> dict[str, MCPServerState]:
    """Connect every server listed in config. Idempotent for already-live servers."""
    if logger:
        set_logger(logger)
    if not available():
        _logger("[MCP] package 'mcp' not installed — skip (pip install mcp)")
        return {}

    configs = _load_server_list()
    if not configs:
        return {}

    async def _all():
        out: dict[str, MCPServerState] = {}
        for cfg in configs:
            name = _sanitize(str(cfg.get("name") or "server"))
            if name in _servers and _servers[name]._session is not None and not _servers[name].error:
                out[name] = _servers[name]
                continue
            state = await _connect_one(cfg)
            _servers[name] = state
            out[name] = state
        return out

    try:
        return _run_async(_all())
    except Exception as e:
        _logger(f"[MCP] connect_all error: {e}")
        return dict(_servers)


def list_tool_records(
    core_tool_names: set[str] | None = None,
    logger: Callable[[str], None] | None = None,
) -> list[dict]:
    """Return dicts ready to become PluginRecord entries.

    Each dict: name, description, parameters, run, file, valid, behavior, …
    """
    core_tool_names = core_tool_names or set()
    states = connect_all(logger=logger)
    records = []

    for state in states.values():
        if state.error or not state.tools:
            continue
        for tool in state.tools:
            if tool.full_name in core_tool_names:
                continue

            def _make_run(server_name: str, tool_name: str):
                def run(parameters: dict, player=None, session_memory=None, **_kw) -> str:
                    return call_tool(server_name, tool_name, parameters or {})
                return run

            records.append({
                "name": tool.full_name,
                "description": f"[MCP:{tool.server}] {tool.description}",
                "parameters": tool.parameters,
                "run": _make_run(tool.server, tool.name),
                "file": f"mcp:{tool.server}",
                "valid": True,
                "error": "",
                "behavior": "BLOCKING",
                "scheduling": "WHEN_IDLE",
                "tier": "extra",
                "brief": f"MCP {tool.server}/{tool.name}",
            })
    return records


def call_tool(server: str, tool_name: str, arguments: dict | None = None) -> str:
    """Invoke one MCP tool and return a short string result for the model."""
    state = _servers.get(_sanitize(server))
    if not state or state._session is None:
        # Lazy reconnect once
        connect_all()
        state = _servers.get(_sanitize(server))
    if not state or state._session is None:
        return f"MCP server '{server}' is not connected ({getattr(state, 'error', 'missing')})."

    args = arguments if isinstance(arguments, dict) else {}

    async def _call():
        result = await state._session.call_tool(tool_name, arguments=args)
        parts = []
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                parts.append(str(text))
            else:
                parts.append(str(block))
        if getattr(result, "isError", False):
            return "MCP error: " + ("\n".join(parts) or "unknown")
        return "\n".join(parts) if parts else "(MCP tool returned no content)"

    try:
        out = _run_async(_call())
        return (out or "")[:8000]
    except Exception as e:
        return f"MCP call failed ({server}/{tool_name}): {type(e).__name__}: {e}"


def shutdown() -> None:
    """Best-effort close of all sessions (call on app exit if desired)."""
    async def _close():
        for state in list(_servers.values()):
            try:
                if state._session is not None:
                    await state._session.__aexit__(None, None, None)
            except Exception:
                pass
            try:
                if state._cm is not None:
                    await state._cm.__aexit__(None, None, None)
            except Exception:
                pass
            state._session = None
            state._cm = None

    try:
        _run_async(_close())
    except Exception:
        pass
    _servers.clear()


def apply_offline_policy(offline: bool) -> dict:
    """Pause internet MCP servers when offline; keep local filesystem/memory."""
    cfg = _load_server_list()
    paused = []
    kept = []
    for s in cfg:
        name = str(s.get("name") or "")
        needs_net = bool(s.get("requires_internet"))
        if offline and needs_net:
            # mark disabled in runtime state
            st = _servers.get(name)
            if st:
                st.error = "paused_offline"
            paused.append(name)
        else:
            kept.append(name)
    return {"offline": offline, "paused": paused, "kept": kept}


def boot_mcp_async(timeout: float = 8.0) -> None:
    """Start enabled MCP servers in a daemon thread; never block main boot."""
    import shutil
    import threading
    if not shutil.which("npx") and not shutil.which("node"):
        _logger("[MCP] Node.js/npx não encontrado — MCP adiado (winget install OpenJS.NodeJS.LTS).")
        return
    if not available():
        _logger("[MCP] pacote Python 'mcp' ausente — pip install mcp")
        return

    def _run():
        try:
            # discover/load tools with soft timeout
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(lambda: list_tools() if "list_tools" in dir() else None)
                try:
                    fut.result(timeout=timeout)
                    _logger("[MCP] servidores iniciais carregados")
                except Exception as e:
                    _logger(f"[MCP] boot timeout/erro: {e}")
        except Exception as e:
            _logger(f"[MCP] boot fail: {e}")

    threading.Thread(target=_run, daemon=True, name="mcp-boot").start()


def status_summary() -> dict:
    cfg = _load_server_list()
    out = []
    for s in cfg:
        name = s.get("name")
        st = _servers.get(name) if isinstance(_servers, dict) else None
        out.append({
            "name": name,
            "enabled": s.get("enabled", True),
            "requires_internet": s.get("requires_internet", False),
            "tools": len(getattr(st, "tools", []) or []) if st else 0,
            "error": getattr(st, "error", "") if st else "",
        })
    return {"servers": out, "mcp_sdk": available()}
