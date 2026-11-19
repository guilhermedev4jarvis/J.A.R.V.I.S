from __future__ import annotations

import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PACK = [
    ("actions.security.honeypot_rede_local", "honeypot_rede_local"),
    ("actions.security.auditor_vazamento_credenciais", "auditor_vazamento_credenciais"),
    ("actions.web_media.monitor_mudanca_pagina", "monitor_mudanca_pagina"),
    ("actions.web_media.extrator_artigo_web", "extrator_artigo_web"),
    ("actions.finance_shopping.comparador_preco_historico", "comparador_preco_historico"),
    ("actions.ai_core.gerador_workflow_automacao", "gerador_workflow_automacao"),
]


def test_front_b_tool_contracts():
    for mod_name, tool_name in PACK:
        mod = importlib.import_module(mod_name)
        tool = mod.TOOL
        assert tool["name"] == tool_name
        assert callable(tool["handler"])
        assert tool["parameters"]["type"] == "OBJECT"


def test_auditor_strength_offline():
    from actions.security.auditor_vazamento_credenciais import auditor_vazamento_credenciais
    r = auditor_vazamento_credenciais({"mode": "auditar_forca", "password": "1234"})
    assert "status=done" in r
    assert "****" in r or "masked" in r or "fraca" in r or "entropy" in r


def test_auditor_never_echoes_password():
    from actions.security.auditor_vazamento_credenciais import auditor_vazamento_credenciais
    secret = "SuperSecretPassword!99"
    r = auditor_vazamento_credenciais({"mode": "auditar_forca", "password": secret})
    assert secret not in r


def test_comparador_preco_flow(tmp_path, monkeypatch):
    import actions.finance_shopping._comparador_preco_historico_impl as impl
    monkeypatch.setattr(impl, "project_root", lambda: tmp_path)
    (tmp_path / "memory").mkdir()
    from actions.finance_shopping.comparador_preco_historico import comparador_preco_historico
    r1 = comparador_preco_historico({"action": "registrar", "produto": "SSD", "preco": 400, "loja": "A"})
    assert "status=done" in r1
    r2 = comparador_preco_historico({"action": "registrar", "produto": "SSD", "preco": 350, "loja": "B"})
    assert "status=done" in r2
    r3 = comparador_preco_historico({"action": "analisar", "produto": "SSD"})
    assert "status=done" in r3
    assert "min" in r3 or "avg" in r3


def test_monitor_ssrf_blocks_localhost():
    from actions.web_media.monitor_mudanca_pagina import monitor_mudanca_pagina
    r = monitor_mudanca_pagina({"action": "adicionar", "url": "http://127.0.0.1/admin", "alias": "x"})
    assert "status=failed" in r


def test_workflow_validate_dry():
    from actions.ai_core.gerador_workflow_automacao import gerador_workflow_automacao
    r = gerador_workflow_automacao({
        "action": "criar_rotina",
        "descricao": "system_health depois web_search",
        "nome_rotina": "teste_wf",
        "dry_run": "true",
    })
    assert "status=done" in r
