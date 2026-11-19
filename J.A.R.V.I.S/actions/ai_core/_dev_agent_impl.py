"""Implementacao do modo dev_agent para o code_studio.

Este modulo estava referenciado em actions/code_studio.py, mas ausente do
projeto. Ele encaminha tarefas de desenvolvimento para o pipeline unificado
core.code_engine, sem executar o codigo gerado por padrao.
"""
from __future__ import annotations

from typing import Any

from core.code_engine import get_engine
from core.outcome import ask, done, failed


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "sim", "on"}


def dev_agent(parameters: dict | None = None, **_ctx) -> str:
    """Executa uma tarefa de desenvolvimento pelo CodeEngine do JARVIS.

    Parametros aceitos:
      - goal/prompt/description: objetivo da tarefa;
      - write: grava os arquivos aprovados pelo sandbox (padrao: true,
        consistente com code_studio mode=pipeline);
      - run: executa os fontes gerados no verificador isolado (padrao: false).
      - dry_run: simula a gravacao sem alterar os arquivos.
    """
    params = dict(parameters or {})
    action = str(params.get("action") or params.get("mode") or "run").strip().lower()

    if action in {"help", "status"}:
        return done(
            "dev_agent",
            engine="core.code_engine",
            modes=["run", "pipeline", "status"],
            default_run=False,
        )

    goal = str(
        params.get("goal")
        or params.get("prompt")
        or params.get("description")
        or params.get("task")
        or ""
    ).strip()
    if not goal:
        return ask("dev_agent", "goal?", hint="Descreva o que deseja desenvolver ou corrigir.")

    write = _as_bool(params.get("write"), default=True)
    run = _as_bool(params.get("run"), default=False)
    dry_run = _as_bool(params.get("dry_run"), default=False)

    try:
        engine = get_engine()
        result = engine.pipeline(
            goal,
            write=write,
            run=run,
            dry_run=dry_run,
        )
        return result.as_outcome("dev_agent")
    except Exception as exc:
        return failed("dev_agent", str(exc), stage="dispatch")
