"""
powershell_cmd — run PowerShell (Windows) or shell (Unix) safely.

Security layers:
  1. core.static_safety.analyze_shell — block destructive patterns
  2. Allowlist prefixes for non-force mode
  3. core.confirm for elevated / borderline commands
  4. core.owner_gate for shutdown/format-class commands
"""
from __future__ import annotations

import platform
import re
import shlex
import subprocess
from typing import Optional

from core.outcome import done, failed, unverified, ask
from core.static_safety import analyze_shell, requires_owner_gate

_OS = platform.system()

_SAFE_PREFIXES_WIN = (
    "get-", "select-", "where-", "foreach-", "measure-", "write-output",
    "write-host", "echo", "dir", "ls", "cat", "type", "pwd", "cd",
    "test-path", "resolve-path", "get-childitem", "get-content",
    "get-process", "get-service", "get-date", "get-location",
    "convertto-json", "convertfrom-json", "out-string",
    "ipconfig", "systeminfo", "whoami", "hostname", "netstat",
    "ping", "nslookup", "tracert", "arp", "route", "net ",
)

_SAFE_PREFIXES_UNIX = (
    "ls", "pwd", "echo", "cat", "head", "tail", "wc", "df", "du", "free",
    "ps", "top", "uptime", "uname", "whoami", "id", "date", "cal",
    "ip", "ifconfig", "ping", "ss", "netstat", "dig", "host",
    "git", "python", "python3", "node", "npm", "pip", "which", "type",
    "find", "grep", "rg", "sed", "awk", "sort", "uniq", "cut", "tr",
)


def _is_safe_prefix(cmd: str) -> bool:
    low = cmd.strip().lower()
    prefixes = _SAFE_PREFIXES_WIN if _OS == "Windows" else _SAFE_PREFIXES_UNIX
    return any(low.startswith(p) for p in prefixes)


def _run_windows(cmd: str, timeout: float) -> tuple[int, str, str]:
    full = [
        "powershell", "-NoProfile", "-NonInteractive",
        "-ExecutionPolicy", "Bypass", "-Command", cmd,
    ]
    try:
        r = subprocess.run(
            full, capture_output=True, text=True, timeout=timeout,
            creationflags=0x08000000 if _OS == "Windows" else 0,
            encoding="utf-8", errors="replace",
        )
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %ss" % timeout
    except Exception as e:
        return 1, "", str(e)


def _run_unix(cmd: str, timeout: float) -> tuple[int, str, str]:
    try:
        parts = shlex.split(cmd, posix=True)
    except ValueError:
        parts = []
    if parts and not any(c in cmd for c in ("|", ";", "&&", "||", ">", "<", "`", "$(")):
        try:
            r = subprocess.run(
                parts, capture_output=True, text=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )
            return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
        except FileNotFoundError:
            return 127, "", "command not found: %s" % parts[0]
        except subprocess.TimeoutExpired:
            return 124, "", "timeout after %ss" % timeout
        except Exception as e:
            return 1, "", str(e)
    try:
        r = subprocess.run(
            ["/bin/bash", "-c", cmd],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %ss" % timeout
    except Exception as e:
        return 1, "", str(e)


def powershell_cmd(parameters=None, **_ctx) -> str:
    params = parameters or {}
    cmd = (params.get("command") or params.get("cmd") or "").strip()
    timeout = float(params.get("timeout") or 30)
    timeout = max(3.0, min(timeout, 120.0))
    force = bool(params.get("force", False))

    if not cmd:
        return failed("powershell_cmd", "command is required")

    report = analyze_shell(cmd)
    if not report.ok:
        return failed("powershell_cmd", report.reason, action="blocked")

    # Owner biometrics for destructive-class commands
    if requires_owner_gate(cmd):
        try:
            from core.owner_gate import OwnerGate
            gate = OwnerGate()
            voice = params.get("owner_voice_path")
            camera = str(params.get("owner_camera") or "").lower() in ("1", "true", "yes")
            if not gate.verify_owner(voice_path=voice, camera=camera):
                return ask(
                    "powershell_cmd",
                    "owner biometrics required",
                    need="owner_biometrics",
                    command=cmd[:120],
                )
        except Exception as e:
            return failed("powershell_cmd", "owner_gate_error: %s" % e)

        try:
            from core import confirm
            if not force:
                ok = confirm.ask(
                    "Shell command requires confirmation:\n%s" % cmd[:300],
                    tool="powershell_cmd",
                )
                if not ok:
                    return failed("powershell_cmd", "user_declined", action="confirm")
        except Exception:
            if not force:
                return ask("powershell_cmd", "confirm destructive command?", command=cmd[:120])

    elif not force and not _is_safe_prefix(cmd):
        try:
            from core import confirm
            ok = confirm.ask(
                "Run non-allowlisted command?\n%s" % cmd[:300],
                tool="powershell_cmd",
            )
            if not ok:
                return failed("powershell_cmd", "user_declined_allowlist", action="confirm")
        except Exception:
            return ask(
                "powershell_cmd",
                "command not in allowlist — confirm or pass force=true",
                command=cmd[:120],
            )

    if _OS == "Windows":
        code, out, err = _run_windows(cmd, timeout)
    else:
        code, out, err = _run_unix(cmd, timeout)

    try:
        from core import audit
        audit.log_event("powershell_cmd", {"cmd": cmd[:200], "code": code})
    except Exception:
        pass

    if code == 124:
        return failed("powershell_cmd", "timeout", command=cmd[:80])
    if code != 0:
        return failed(
            "powershell_cmd",
            err or ("exit_%s" % code),
            returncode=code,
            stdout=out[:1500],
            stderr=err[:1500],
        )
    if not out and not err:
        return unverified("powershell_cmd", "empty output", returncode=code)
    return done(
        "powershell_cmd",
        returncode=code,
        stdout=out[:4000],
        stderr=err[:1000],
        platform=_OS,
    )


_LEGACY_TOOL = {
    "name": "powershell_cmd",
    "description": (
        "Executa comando PowerShell (Windows) ou shell (Unix) com allowlist, "
        "blocklist estatica, confirm e owner_gate para acoes destrutivas. "
        "Passe command=...; force=true so apos confirmacao consciente."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {"type": "STRING"},
            "cmd": {"type": "STRING"},
            "timeout": {"type": "NUMBER"},
            "force": {"type": "BOOLEAN"},
            "owner_voice_path": {"type": "STRING"},
            "owner_camera": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": powershell_cmd,
    "tier": "core",
    "risk": "destructive",
}
