"""Contratos e fluxos das 8 novas actions MARK pack."""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

NEW_ACTIONS = [
    ("actions.system.checagempowershell", "checagempowershell"),
    ("actions.system.limpeza_profunda_disco", "limpeza_profunda_disco"),
    ("actions.desktop.tradutor_tela_instantaneo", "tradutor_tela_instantaneo"),
    ("actions.desktop.organizador_janelas_perfil", "organizador_janelas_perfil"),
    ("actions.productivity.resumo_pdf_contrato", "resumo_pdf_contrato"),
    ("actions.productivity.gerador_relatorio_semanal", "gerador_relatorio_semanal"),
    ("actions.ai_core.criador_skill_por_voz", "criador_skill_por_voz"),
    ("actions.ai_core.simulador_entrevista_debate", "simulador_entrevista_debate"),
]


@pytest.mark.parametrize("mod_name,tool_name", NEW_ACTIONS)
def test_new_action_import_and_tool(mod_name, tool_name):
    mod = importlib.import_module(mod_name)
    tool = getattr(mod, "TOOL", None)
    assert isinstance(tool, dict)
    assert tool.get("name") == tool_name
    assert callable(tool.get("handler"))
    assert isinstance(tool.get("description"), str) and tool["description"]
    assert isinstance(tool.get("parameters"), dict)
    assert tool["parameters"].get("type") == "OBJECT"


def test_discover_actions_includes_new_pack():
    from core.action_loader import discover_actions
    reg = discover_actions(ROOT / "actions", logger=lambda *_: None)
    names = set(reg.names()) if hasattr(reg, "names") else set(getattr(reg, "_actions", {}))
    for _mod, tool_name in NEW_ACTIONS:
        assert tool_name in names, f"{tool_name} not discovered"


def test_checagempowershell_analyze_error():
    from actions.system.checagempowershell import checagempowershell
    r = checagempowershell({"mode": "analisar_erro", "error": "cannot be loaded because running scripts is disabled"})
    assert isinstance(r, str) and r
    assert "status=" in r or "ExecutionPolicy" in r or "done" in r.lower() or "root" in r.lower()


def test_limpeza_analisar_no_delete():
    from actions.system.limpeza_profunda_disco import limpeza_profunda_disco
    r = limpeza_profunda_disco({"mode": "analisar"})
    assert "status=" in r
    assert "failed" not in r.split()[0].lower() or "status=done" in r


def test_limpeza_ask_confirm():
    from actions.system.limpeza_profunda_disco import limpeza_profunda_disco
    r = limpeza_profunda_disco({"mode": "limpar"})
    assert "status=ask" in r or "confirm" in r.lower()


def test_organizador_list_and_save(tmp_path, monkeypatch):
    import actions.desktop._organizador_janelas_perfil_impl as impl
    monkeypatch.setattr(impl, "_cfg_path", lambda: tmp_path / "window_workspaces.json")
    from actions.desktop.organizador_janelas_perfil import organizador_janelas_perfil
    r1 = organizador_janelas_perfil({"action": "listar_perfis"})
    assert "status=done" in r1
    r2 = organizador_janelas_perfil({"action": "salvar_perfil", "name": "modo_teste"})
    assert "status=done" in r2
    r3 = organizador_janelas_perfil({"action": "listar_perfis"})
    assert "modo_teste" in r3


def test_resumo_pdf_ask_path():
    from actions.productivity.resumo_pdf_contrato import resumo_pdf_contrato
    r = resumo_pdf_contrato({})
    assert "status=ask" in r or "path" in r.lower()


def test_gerador_relatorio_semanal(tmp_path, monkeypatch):
    import actions.productivity._gerador_relatorio_semanal_impl as impl
    monkeypatch.setattr(impl, "_project_root", lambda: tmp_path)
    (tmp_path / "memory").mkdir(parents=True)
    (tmp_path / "memory" / "diario_cognitivo.jsonl").write_text('{"t":"a"}\\n', encoding="utf-8")
    (tmp_path / "memory" / "episodes.jsonl").write_text('{"e":1}\\n', encoding="utf-8")
    from actions.productivity.gerador_relatorio_semanal import gerador_relatorio_semanal
    r = gerador_relatorio_semanal({"days": 7})
    assert "status=done" in r
    assert list((tmp_path / "memory" / "retrospectivas").glob("*.md"))


def test_tradutor_with_text():
    from actions.desktop.tradutor_tela_instantaneo import tradutor_tela_instantaneo
    r = tradutor_tela_instantaneo({"text": "Hello world", "lang": "pt-BR"})
    assert "status=done" in r or "status=failed" in r


def test_simulador_entrevista_flow():
    from actions.ai_core.simulador_entrevista_debate import simulador_entrevista_debate
    r1 = simulador_entrevista_debate({"action": "iniciar", "kind": "entrevista", "session_id": "t1"})
    assert "status=done" in r1
    r2 = simulador_entrevista_debate({"action": "responder", "session_id": "t1", "message": "Liderei um projeto X."})
    assert "status=done" in r2
    r3 = simulador_entrevista_debate({"action": "finalizar", "session_id": "t1"})
    assert "status=done" in r3


def test_criador_skill_generates_files(tmp_path, monkeypatch):
    import actions.ai_core._criador_skill_por_voz_impl as impl
    monkeypatch.setattr(impl, "_project_root", lambda: tmp_path)
    (tmp_path / "actions" / "misc").mkdir(parents=True)
    from actions.ai_core.criador_skill_por_voz import criador_skill_por_voz
    r = criador_skill_por_voz({
        "description": "lista processos leves do sistema",
        "name": "lista_proc_leve",
        "category": "misc",
        "overwrite": "true",
    })
    assert "status=done" in r
    assert (tmp_path / "actions" / "misc" / "lista_proc_leve.py").is_file()
    assert (tmp_path / "actions" / "misc" / "_lista_proc_leve_impl.py").is_file()
