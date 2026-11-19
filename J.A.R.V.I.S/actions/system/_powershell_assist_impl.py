"""
powershell_assist — shell/PowerShell unificado.

Junta:
  • powershell_cmd        — comando curto e direto (allowlist + force)
  • powershell_generator  — linguagem natural → script .ps1 → validar → executar

Uma única _LEGACY_TOOL para o modelo. Escolha automática:
  - Se vier `command`/`cmd` (e não `intent`) → caminho rápido (cmd)
  - Se vier `intent` / action generate|heal|run → gerador de scripts
  - action=status agrega os dois

Os módulos originais continuam no disco; este arquivo só orquestra.
"""
from __future__ import annotations

from core.outcome import done, failed, ask

from actions.powershell_cmd import powershell_cmd
from actions.powershell_generator import powershell_generator


def _is_intent_heavy(text: str) -> bool:
    """Heuristic: multi-step / natural language → generator."""
    t = (text or "").strip()
    if not t:
        return False
    if "\n" in t or len(t) > 160:
        return True
    # Portuguese / English verbs that suggest multi-step automation
    keys = (
        "backup", "compact", "zip", "limpe", "limpar", "apague", "delete",
        "copie", "copy", "mova", "move", "agende", "schedule", "relatório",
        "report", "para cada", "foreach", "recursiv", "mais de", "older than",
        "faça um", "fazer um", "crie um script", "automati",
    )
    low = t.lower()
    return any(k in low for k in keys)


def powershell_assist(parameters: dict | None = None, **_ctx) -> str:
    params = dict(parameters or {})
    action = (params.get("action") or "").strip().lower()

    command = (params.get("command") or params.get("cmd") or "").strip()
    intent = (params.get("intent") or params.get("request") or params.get("prompt") or "").strip()
    script = (params.get("script") or "").strip()

    # ── explicit status ───────────────────────────────────────────────────
    if action in ("status", "history"):
        gen = powershell_generator({"action": "status"})
        return done(
            "powershell_assist",
            action="status",
            generator=_clip(gen),
            note=(
                "Use action=cmd with command=... for short shell lines; "
                "action=run/generate with intent=... for multi-step scripts."
            ),
        )

    # ── force path: cmd ───────────────────────────────────────────────────
    if action in ("cmd", "command", "shell", "exec_cmd", "run_cmd"):
        if not command and intent and not _is_intent_heavy(intent):
            # treat short intent as the command itself
            params = {**params, "command": intent}
        elif not command:
            return failed("powershell_assist", "command is required for action=cmd")
        return _as_assist(powershell_cmd(params), via="cmd")

    # ── force path: generator ─────────────────────────────────────────────
    if action in ("generate", "preview", "draft", "heal", "fix", "repair", "run", "execute", "script"):
        if action in ("run", "execute") and command and not intent and not script:
            # user said run but only passed a one-liner command
            if not _is_intent_heavy(command):
                return _as_assist(powershell_cmd({**params, "command": command}), via="cmd")
        if not intent and not script and command:
            params = {**params, "intent": command}
        if action in ("run", "execute"):
            params = {**params, "action": "run"}
        elif action in ("fix", "repair"):
            params = {**params, "action": "heal"}
        else:
            params = {**params, "action": action}
        return _as_assist(powershell_generator(params), via="generator")

    # ── auto route ────────────────────────────────────────────────────────
    if script or (intent and (not command or _is_intent_heavy(intent))):
        p = {**params, "action": "run"}
        if intent:
            p["intent"] = intent
        if script:
            p["script"] = script
        return _as_assist(powershell_generator(p), via="generator")

    if command:
        if _is_intent_heavy(command):
            return _as_assist(
                powershell_generator({**params, "action": "run", "intent": command}),
                via="generator",
            )
        return _as_assist(powershell_cmd({**params, "command": command}), via="cmd")

    if intent:
        if _is_intent_heavy(intent):
            return _as_assist(
                powershell_generator({**params, "action": "run", "intent": intent}),
                via="generator",
            )
        # short phrase: try as direct command
        return _as_assist(
            powershell_cmd({**params, "command": intent}),
            via="cmd",
        )

    return ask(
        "powershell_assist",
        "what should I run?",
        options=(
            "cmd (command='Get-Process') | "
            "run (intent='backup folder X to Y and zip') | "
            "generate (preview only) | heal | status"
        ),
    )


def _clip(s: str, n: int = 400) -> str:
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def _as_assist(result: str, via: str) -> str:
    """Tag outcome with via= without breaking the status= protocol."""
    if not result:
        return failed("powershell_assist", "empty subsystem result", via=via)
    if result.startswith("status="):
        # inject via= after action=... if present
        if " via=" not in result:
            parts = result.split(" ", 2)
            if len(parts) >= 2:
                return f"{parts[0]} {parts[1]} via={via} " + (parts[2] if len(parts) > 2 else "")
            return result + f" via={via}"
        return result
    # confirm.py plain sentence or other
    return result


_LEGACY_TOOL = {
    "name": "powershell_assist",
    "description": (
        "Unified Windows PowerShell / shell tool. "
        "SHORT commands: pass command='Get-ChildItem C:\\' (or action=cmd). "
        "Uses an allowlist; destructive lines need force=true after user OK. "
        "COMPLEX / natural language: pass intent='backup D:\\Fotos to \\\\NAS, zip, delete files older than 30 days' "
        "(or action=run/generate). Generates a .ps1, scans for dangerous ops "
        "(confirm.py gate), can elevate with elevate=true, saves under cache/ps_scripts/, "
        "executes and can auto-heal once on failure. "
        "Prefer this single tool instead of powershell_cmd or powershell_generator. "
        "Actions: cmd | run | generate | heal | status. "
        "On non-Windows, cmd uses bash; script generation still targets PowerShell and execution requires Windows."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "cmd | run | generate | heal | status (optional — auto-detected from fields)",
            },
            "command": {
                "type": "STRING",
                "description": "Exact short shell/PowerShell line for action=cmd",
            },
            "cmd": {
                "type": "STRING",
                "description": "Alias for command",
            },
            "intent": {
                "type": "STRING",
                "description": "Natural language multi-step task for script generation",
            },
            "script": {
                "type": "STRING",
                "description": "Ready-made PowerShell body to validate/run",
            },
            "timeout": {
                "type": "NUMBER",
                "description": "Seconds (cmd default ~30, scripts default ~120)",
            },
            "force": {
                "type": "BOOLEAN",
                "description": "Required for non-allowlisted cmd or after confirming dangerous script",
            },
            "elevate": {
                "type": "BOOLEAN",
                "description": "Request Admin UAC when running a generated script",
            },
            "auto_heal": {
                "type": "BOOLEAN",
                "description": "On script failure, one LLM repair+rerun (default true)",
            },
            "error_context": {
                "type": "STRING",
                "description": "For heal: previous stderr / script",
            },
        },
        "required": [],
    },
    "handler": powershell_assist,
    "tier": "core",
}
