"""Diagnóstico de erros do PowerShell (Windows)."""
from __future__ import annotations

import platform
import re
import subprocess
from typing import Any

from core.outcome import ask, done, failed

_OS = platform.system()


def _run_ps(script: str, timeout: int = 12) -> tuple[int, str, str]:
    if _OS != "Windows":
        return 1, "", "PowerShell diagnostics requer Windows."
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=0x08000000,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except FileNotFoundError:
        return 1, "", "powershell nao encontrado no PATH"
    except subprocess.TimeoutExpired:
        return 1, "", "timeout ao consultar PowerShell"
    except Exception as e:
        return 1, "", str(e)[:200]


def _analyze_text(err: str) -> dict[str, Any]:
    low = (err or "").lower()
    if "executionpolicy" in low or "cannot be loaded" in low or "nao pode ser carregado" in low:
        return {
            "root_cause": "ExecutionPolicy restritiva",
            "fix_command": "Set-ExecutionPolicy -Scope CurrentUser RemoteSigned",
            "tips": ["Politica de execucao bloqueia scripts .ps1."],
        }
    if "module" in low and ("not found" in low or "nao encontrado" in low or "não encontrado" in low):
        m = re.search(r"module[s]?\s+([A-Za-z0-9_.-]+)", err or "", re.I)
        mod = m.group(1) if m else "NomeDoModulo"
        return {
            "root_cause": "modulo ausente",
            "fix_command": f"Install-Module -Name {mod} -Scope CurrentUser -Force",
            "tips": [f"Instale o modulo: {mod}"],
        }
    if "access is denied" in low or "acesso negado" in low:
        return {
            "root_cause": "permissao negada",
            "fix_command": "Start-Process powershell -Verb RunAs",
            "tips": ["Abra o PowerShell como Administrador."],
        }
    if "cannot find path" in low or "caminho" in low:
        return {
            "root_cause": "caminho invalido",
            "fix_command": "Test-Path 'C:\\caminho'; Get-ChildItem",
            "tips": ["Verifique caminho e aspas."],
        }
    if "parsererror" in low or "syntax" in low:
        return {
            "root_cause": "erro de sintaxe",
            "fix_command": "Get-Help about_Parsing",
            "tips": ["Revise aspas, pipes e blocos."],
        }
    return {
        "root_cause": "erro generico",
        "fix_command": "Get-Error | Format-List * -Force",
        "tips": ["Sem padrao conhecido."],
    }


def run(parameters=None, **_ctx) -> str:
    params = dict(parameters or {})
    mode = str(params.get("mode") or params.get("action") or "historico").strip().lower()
    error_text = str(params.get("error") or params.get("text") or params.get("query") or "").strip()

    if _OS != "Windows" and mode != "analisar_erro":
        return done(
            "checagempowershell",
            status="unsupported_os",
            message="Logs nativos so no Windows. Use mode=analisar_erro.",
            os=_OS,
        )

    if mode in ("analisar_erro", "analyze", "erro"):
        if not error_text:
            return ask("checagempowershell", "Cole a mensagem de erro do PowerShell.")
        return done(
            "checagempowershell",
            mode=mode,
            error_excerpt=error_text[:400],
            **_analyze_text(error_text),
        )

    if mode in ("logs_sistema", "logs", "winevent"):
        script = (
            "try { Get-WinEvent -LogName 'Microsoft-Windows-PowerShell/Operational' "
            "-MaxEvents 15 -ErrorAction Stop | "
            "Where-Object { $_.LevelDisplayName -in @('Error','Warning') } | "
            "Select-Object -First 8 TimeCreated, Id, LevelDisplayName, Message | "
            "Format-List | Out-String -Width 200 } catch { $_.Exception.Message }"
        )
        code, out, err = _run_ps(script)
        blob = out or err
        return done(
            "checagempowershell",
            mode=mode,
            ok=code == 0,
            events_preview=(blob or "")[:1500],
            **_analyze_text(blob),
        )

    script = (
        "$hist = Join-Path $env:APPDATA "
        "'Microsoft/Windows/PowerShell/PSReadLine/ConsoleHost_history.txt'; "
        "if (Test-Path $hist) { Get-Content $hist -Tail 20 | Out-String } "
        "else { 'history_not_found' }"
    )
    code, out, err = _run_ps(script)
    hist = out or err or ""
    return done(
        "checagempowershell",
        mode="historico",
        ok=code == 0,
        history_tail=hist[:1200],
        **_analyze_text(hist),
    )
