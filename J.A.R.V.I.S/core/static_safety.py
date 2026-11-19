"""
core/static_safety.py — static analysis gates before code/shell execution.

Used by powershell_cmd, self_program, and any future executor.
Does not replace owner_gate / confirm for irreversible OS actions.
"""
from __future__ import annotations

import ast
import re
from typing import Any, Optional

# Python AST: dangerous calls / imports
_DANGEROUS_IMPORTS = frozenset({
    "ctypes", "cffi", "winreg", "msvcrt",
})
_DANGEROUS_FROM = frozenset({
    ("os", "system"), ("os", "popen"), ("os", "remove"), ("os", "removedirs"),
    ("os", "rmdir"), ("os", "unlink"), ("shutil", "rmtree"), ("shutil", "move"),
    ("subprocess", "call"), ("subprocess", "run"), ("subprocess", "Popen"),
    ("pathlib", "Path"),  # not always dangerous; checked with call context
})
_DANGEROUS_ATTR = frozenset({
    "system", "popen", "rmtree", "remove", "unlink", "removedirs",
    "format", "mkfs", "shutdown",
})
_DANGEROUS_NAMES = frozenset({
    "eval", "exec", "compile", "__import__", "breakpoint",
    "input",  # only flagged in strict mode
})

# Shell / PowerShell blocklist (extended)
_SHELL_BLOCKED = (
    r"format\s+[a-z]:",
    r"remove-item\s+.*(-recurse|-r).*(\\windows|\\system32|/etc|/usr)",
    r"rm\s+-rf\s+/(etc|usr|var|boot|sys|dev)?(\s|$)",
    r"rm\s+-rf\s+~/?\s*$",
    r"shutdown",
    r"restart-computer",
    r"stop-computer",
    r"disable-computerrestore",
    r"clear-disk",
    r"reset-computermachinepassword",
    r"remove-computer",
    r"cipher\s+/w",
    r"dd\s+if=",
    r"mkfs\.",
    r"diskpart",
    r"reg\s+delete",
    r"net\s+user\s+\w+\s+/delete",
    r"Invoke-Expression",
    r"iex\s*\(",
    r"DownloadString",
    r"FromBase64String",
    r"Start-Process\s+.*-Verb\s+RunAs",
    r":\(\)\s*\{\s*:\|:&\s*\};:",
    r"chmod\s+-R\s+777\s+/",
    r"chown\s+-R\s+.*\s+/",
    r">\s*/etc/",
    r"curl\s+.*\|\s*(ba)?sh",
    r"wget\s+.*\|\s*(ba)?sh",
)


class SafetyReport:
    def __init__(self, ok: bool, reason: str = "", severity: str = "info"):
        self.ok = ok
        self.reason = reason
        self.severity = severity  # info | warn | block

    def __repr__(self) -> str:
        return "SafetyReport(ok=%s, severity=%s, reason=%r)" % (self.ok, self.severity, self.reason)


def analyze_python(source: str, *, strict: bool = False) -> SafetyReport:
    """AST scan. Returns ok=False when execution should be refused."""
    if not source or not source.strip():
        return SafetyReport(False, "empty_source", "block")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return SafetyReport(False, "syntax_error: %s" % e, "block")

    issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = (alias.name or "").split(".")[0]
                if root in _DANGEROUS_IMPORTS:
                    issues.append("import:%s" % root)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                if (mod, alias.name) in _DANGEROUS_FROM and alias.name in (
                    "system", "popen", "rmtree", "remove", "unlink", "call", "Popen", "run"
                ):
                    issues.append("from %s import %s" % (mod, alias.name))
        elif isinstance(node, ast.Call):
            fn = node.func
            name = None
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                name = fn.attr
            if name in ("eval", "exec", "compile", "__import__"):
                issues.append("call:%s" % name)
            if name in _DANGEROUS_ATTR and strict:
                issues.append("attr_call:%s" % name)
        elif isinstance(node, ast.Name) and node.id in ("eval", "exec") and isinstance(node.ctx, ast.Load):
            issues.append("name:%s" % node.id)

    if issues:
        # eval/exec always block; others block in strict or when clearly destructive
        hard = [i for i in issues if i.startswith("call:eval") or i.startswith("call:exec")
                or i.startswith("call:__import__") or "rmtree" in i or "system" in i]
        if hard:
            return SafetyReport(False, "blocked: " + ", ".join(hard[:6]), "block")
        if strict:
            return SafetyReport(False, "blocked: " + ", ".join(issues[:8]), "block")
        return SafetyReport(True, "warn: " + ", ".join(issues[:8]), "warn")
    return SafetyReport(True, "ok", "info")


def analyze_shell(command: str) -> SafetyReport:
    """Block destructive shell/PowerShell patterns."""
    cmd = (command or "").strip()
    if not cmd:
        return SafetyReport(False, "empty_command", "block")
    low = cmd.lower()
    for pat in _SHELL_BLOCKED:
        if re.search(pat, low, re.I):
            return SafetyReport(False, "blocked pattern: %s" % pat, "block")
    # Pipe-to-shell
    if re.search(r"\|\s*(ba)?sh\b", low) or re.search(r"\|\s*powershell\b", low):
        return SafetyReport(False, "blocked pipe-to-shell", "block")
    return SafetyReport(True, "ok", "info")


def requires_owner_gate(command: str) -> bool:
    """True when command should demand biometrics even if not fully blocked."""
    low = (command or "").lower()
    keys = (
        "shutdown", "restart", "reboot", "format", "diskpart", "rm -rf",
        "remove-item", "stop-computer", "clear-disk", "mkfs", "cipher /w",
        "reg delete", "net user",
    )
    return any(k in low for k in keys)
