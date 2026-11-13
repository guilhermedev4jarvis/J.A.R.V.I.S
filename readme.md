# J.A.R.V.I.S. — MARK LXI (61)

### Assistente virtual e agente autônomo de desktop

Este repositório contém o código-fonte e a arquitetura do **J.A.R.V.I.S. — MARK LXI (61)**:
um assistente que **ouve, vê, fala e controla o computador** em **Windows, macOS e Linux**.

Por padrão usa a API **Gemini Live** para voz em tempo real. Sem cota, sem rede ou em modo
air-gapped, o mesmo avatar, memória, confirmações e tools continuam com motor **100% local**
(Ollama + STT/TTS locais) em **⚙ → ENGINE & PROVIDERS**. Modelo local padrão: **`qwen2.5-coder:7b`**.

Não há servidor J.A.R.V.I.S. na nuvem, telemetria obrigatória nem assinatura. O que você não
usa (providers extras, wake word, dashboard no celular) **não é carregado** na inicialização.

**Autoria:** Guilherme · **Licença:** [CC BY-NC 4.0](LICENSE)

---

## Índice

1. [Visão geral](#visão-geral)
2. [Biometria do dono](#biometria-do-dono)
3. [Tools unificadas](#tools-unificadas)
4. [Estrutura do projeto](#estrutura-do-projeto)
5. [Requisitos e instalação](#requisitos-e-instalação)
6. [Dashboard e autonomia](#dashboard-e-autonomia)
7. [Dados e privacidade](#dados-e-privacidade)
8. [Licença e autoria](#licença-e-autoria)

---

## Visão geral

| Capacidade | Descrição |
|------------|-----------|
| Voz em tempo real | Gemini Live com fallback offline (Ollama / Whisper / Piper) |
| Biometria | Face → voz sequencial no boot (threshold voz **0.75**) |
| Desktop | Controle de janelas, apps, PowerShell com safety, layouts |
| Missões | `mission_planner` + `context_triggers` + loop proativo |
| Visão | OCR (`screenshot_ocr`) e análise multimodal (`screen_context_advisor`) |
| Dev | `git_voice_copilot`, `code_studio`, engines Roblox / Blender / Godot |
| Segurança | `owner_gate`, sandbox, audit, `intruder_alert`, vault |

---

## Biometria do dono

1. **Face** — captura e validação via `core/face_auth.py` (overlay na UI + TTS *“Começando biometria facial.”*).
2. **Voz** — após a face, TTS *“Começando biometria de voz.”* e validação com threshold **0.75**
   (`core/voice_auth.py`, perfil em `memory/biometrics/`).
3. Falha → botão **Tentar novamente**; sucesso → acesso liberado e HUD principal.

Wake words locais (opcional): “Jarvis”, “J.A.R.V.I.S.”, “Mark LXI”, “Hey Jarvis”.

---

## Tools unificadas

Actions públicas em `actions/` (contrato `TOOL` + `core.outcome`). Principais no **MARK LXI (61)**:

### Produtividade e conhecimento
| Tool | Função |
|------|--------|
| `mission_planner` | Missões multi-etapas (plan / run / resume) |
| `routine_orchestrator` | Macros em `config/routines.json` |
| `local_doc_rag` | PDF · DOCX · TXT · MD locais |
| `meeting_transcriber` | Gravação / transcrição / action items |

### Visão e tela
| Tool | Função |
|------|--------|
| `screenshot_ocr` | OCR rápido de texto |
| `screen_context_advisor` | Análise visual multimodal (Gemini) |
| `screen_memory_timeline` | Timeline privada título + OCR |

### Autonomia
| Tool | Função |
|------|--------|
| `context_triggers` | Gatilhos app / bateria / ociosidade |
| `webhook_bridge` | ntfy · Discord · Home Assistant |
| `intruder_alert` | Guardião de ausência |

### Sistema e áudio
| Tool | Função |
|------|--------|
| `desktop_control` / `window_workspace_saver` | Desktop e layouts |
| `app_audio_mixer` | Volume / mute por app (Windows) |
| `power_profile_manager` | Energia e brilho |
| `whatsapp_web` | WhatsApp Web (abrir / contato / enviar) |

### Desenvolvimento e segurança
| Tool | Função |
|------|--------|
| `git_voice_copilot` | status · diff · commit · push |
| `secure_vault_helper` | Segredos → clipboard com TTL |
| `code_studio` / `powershell_tool` | Código e shell com safety |

---

## Estrutura do projeto

```
J.A.R.V.I.S/
├── main.py              # entrypoint
├── ui.py                # HUD / overlay biométrico
├── actions/             # tools (TOOL + handler)
├── core/                # outcome, secrets, gemini, biometrics, sandbox
├── providers/           # STT / TTS / LLM
├── memory/              # long-term, biometrics, missions, audit
├── dashboard/           # server + static HUD web
├── config/              # api_keys, routines, triggers, webhooks
├── site/                # landing page
├── tests/               # pytest
├── readme.md · AUTORIA.md · LICENSE
└── setup.py
```

---

## Requisitos e instalação

**Python 3.10+** recomendado.

```bash
# Núcleo (leve)
pip install -r requirements.txt

# Offline / voz local
pip install -r requirements-local.txt

# Completo (visão, GPU, dados)
pip install -r requirements-heavy.txt
```

Configure a chave Gemini em `.env` (`MARK_GEMINI_API_KEY` / `GEMINI_API_KEY`) ou
`config/api_keys.json` (nunca commitar segredos).

```bash
python main.py
# testes
python -m pytest tests/ -q
```

---

## Dashboard e autonomia

- Dashboard local: `dashboard/server.py` + `dashboard/static/app.html`
- APIs: missões, gatilhos, timeline, áudio, guardião (`/api/...`, autenticadas)
- Loop proativo: `actions/proactive.py` + task em `main.py` (triggers + timeline opcional)

---

## Dados e privacidade

- Memória e biometria ficam **locais** (`memory/`)
- Redaction de segredos em logs (`core/redaction.py`)
- Sem telemetria obrigatória do J.A.R.V.I.S.

---

## Licença e autoria

- **J.A.R.V.I.S. — MARK LXI (61)**
- **© 2026 Guilherme**
- **CC BY-NC 4.0** — ver [LICENSE](LICENSE) e [AUTORIA.md](AUTORIA.md)

Uso comercial não permitido sem autorização do autor.
