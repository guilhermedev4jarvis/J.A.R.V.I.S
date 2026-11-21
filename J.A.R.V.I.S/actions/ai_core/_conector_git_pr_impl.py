"""Controle de versao seguro para evolucoes autonomas do J.A.R.V.I.S."""
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from core.outcome import done, failed

_BASE = Path(__file__).resolve().parents[2]


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(_BASE),
        capture_output=True,
        text=True,
        check=False,
    )


def run(parameters=None, player=None, session_memory=None, **ctx):
    params = parameters or {}
    action = str(params.get("action") or "status").lower()
    message = str(params.get("message") or "chore(jarvis): auto-checkpoint").strip()
    confirmed = bool(params.get("confirmed", False))

    if not (_BASE / ".git").exists():
        return done("conector_git_pr", "Repositorio Git nao inicializado nesta pasta.", {"git_initialized": False})

    if action == "create_branch":
        branch = f"jarvis/auto-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        res = _git("checkout", "-b", branch)
        if res.returncode != 0:
            return failed("conector_git_pr", res.stderr.strip() or "Falha ao criar branch.")
        return done("conector_git_pr", f"Branch '{branch}' criada e ativa.", {"branch": branch})

    if action == "commit":
        _git("add", "-A")
        res = _git("commit", "-m", message)
        if res.returncode != 0:
            return done("conector_git_pr", "Nenhuma alteracao pendente para commit.", {"output": res.stdout.strip()})
        try:
            from core import audit
            audit.log_event("git_auto_commit", {"message": message})
        except Exception:
            pass
        return done("conector_git_pr", f"Commit registrado: {message}", {"output": res.stdout.strip()})

    if action == "rollback":
        if not confirmed:
            return failed("conector_git_pr", "Confirmacao explicita necessaria (confirmed=True) para rollback.")
        res = _git("reset", "--hard", "HEAD~1")
        if res.returncode != 0:
            return failed("conector_git_pr", res.stderr.strip() or "Falha ao executar rollback.")
        return done("conector_git_pr", "Rollback para HEAD~1 concluido.", {"output": res.stdout.strip()})

    st = _git("status", "--short")
    br = _git("rev-parse", "--abbrev-ref", "HEAD")
    return done(
        "conector_git_pr",
        f"Git ativo na branch '{br.stdout.strip()}'.",
        {"branch": br.stdout.strip(), "changes": st.stdout.strip().splitlines()},
    )