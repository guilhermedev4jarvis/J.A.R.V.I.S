# MARK LVI (56)

### Assistente virtual e agente autônomo de desktop

Este repositório contém o código-fonte e a arquitetura do **MARK LVI (56)** (JARVIS): um assistente que **ouve, vê, fala e controla o computador** em **Windows, macOS e Linux**.

Por padrão usa a API **Gemini Live** para voz em tempo real. Sem cota, sem rede ou em modo air-gapped, o mesmo avatar, memória, confirmações e tools continuam com motor **100% local** (Ollama + STT/TTS locais) em **⚙ → ENGINE & PROVIDERS**. Modelo local padrão: **`qwen2.5-coder:7b`**.

Não há servidor MARK LVI na nuvem, telemetria obrigatória nem assinatura. O que você não usa (providers extras, wake word, dashboard no celular) **não é carregado** na inicialização.

---

## Índice

1. [Visão geral](#visão-geral)
2. [Novidades (camadas de qualidade)](#novidades-camadas-de-qualidade)
3. [Biometria do dono](#biometria-do-dono)
4. [Tools unificadas](#tools-unificadas)
5. [Estrutura do projeto](#estrutura-do-projeto)
6. [Requisitos e instalação](#requisitos-e-instalação)
7. [Como estender](#como-estender)
8. [Dados e privacidade](#dados-e-privacidade)
9. [Ideias para o próximo passo](#ideias-para-o-próximo-passo)
10. [Licença e autoria](#licença-e-autoria)

---

## Visão geral

| Capacidade | Descrição |
|---|---|
| Voz em tempo real | Gemini Live **ou** pipeline local (STT → LLM → TTS) |
| Modelo local padrão | Ollama **`qwen2.5-coder:7b`** |
| Avatar holográfico | Cabeça 3D no HUD, lip-sync — software only, sem GPU obrigatória |
| Wake word | “Hey Jarvis” / “Mark LVI” local e opcional |
| Memória | Fatos (`long_term.json`) + **episódios** + **grafo** de entidades |
| Undo e confirmação | Gate no HUD; o modelo **não** forja o “sim” |
| Outcomes honestos | `done` / `unverified` / `failed` / `ask` / `started` com base no **observado** |
| Actions e plugins | Cada arquivo em `actions/` ou `plugins/` é descoberto automaticamente |
| MCP | Tools externas via Model Context Protocol (`core/mcp_client.py`) |
| OpenAI Realtime | Engine de áudio nativo opcional |
| Desktop agent | Loop **Observar → Agir → Validar** (fingerprint de tela) |
| Biometria do dono | Voz (`vozdono.mp3`) + 3 fotos + gate em shutdown/restart |
| Modos de operação | `listen` / `assist` / `autonomous` (+ air-gapped) |
| Dashboard no celular | Painel local (`dashboard/`) com QR |

---

## Novidades (camadas de qualidade)

Detalhes em `UPGRADE_4_FEATURES.md` e `UPGRADE_QUALITY_LAYERS.md`.

### Confiabilidade
- **`core/contracts.py`** — risk tiers (`safe` / `review` / `destructive` / `autonomous`)
- **`core/retry.py`** — backoff + circuit breaker
- **`core/sandbox.py`** — dry-run e política de paths
- Testes: `tests/test_action_contracts.py`, `tests/test_quality_layers.py`

### Memória
- Episódios + grafo (`memory/memory_manager.py`)
- `consolidate` / `hygiene` / `forget_old` via `memory_compactor`

### Voz e fallback
- `audio_latency_tuner` com `action=auto`
- `core/network_fallback.py` — nuvem → local quando a rede cai

### Segurança
- **`core/redaction.py`** — mascara secrets nos logs
- **`core/audit.py`** — JSONL diário em `memory/audit/`
- **`core/owner_gate.py`** — biometria em ações críticas
- **`core/agent_mode.py`** — listen-only e air-gapped

### Extensão
- `python scripts/new_module.py action|plugin nome`
- Hot-reload isolado (`hot_reload`)
- MCP examples em `config/mcp_servers.json.example`

---

## Biometria do dono

Na **primeira inicialização**, se faltar cadastro em `memory/biometrics/`:

| Arquivo | Conteúdo |
|---------|----------|
| `vozdono.mp3` | Sua voz dizendo o comando (“ok jarvis”, “acorda jarvis”, …) |
| `fotobase1.jpg` | Rosto de frente |
| `fotobase2.jpg` | Rosto de um lado |
| `fotobase3.jpg` | Rosto do outro lado |
| `owner_command.json` | Frase escolhida |

```text
owner_setup action=set_phrase phrase="ok jarvis"
owner_setup action=enroll_voice path=/caminho/gravacao.wav
owner_setup action=enroll_face slot=1 image_path=/fotos/frente.jpg
owner_setup action=enroll_face slot=2 ...
owner_setup action=enroll_face slot=3 ...
```

**Shutdown / restart / reset** exigem biometria (**voz OU câmera/foto**) e depois o CONFIRM no HUD:

```text
computer_settings action=shutdown owner_voice_path=/tmp/eu.wav
computer_settings action=restart  owner_camera=true
```

Guia completo: `docs_OWNER_BIOMETRICS.md`.

---

## Tools unificadas

Preferir tools com **outcomes honestos** e risk declarado. Exemplos de famílias:

**Desktop e agente**
- `desktop_agent` — plano multi-step com validação de tela
- `computer_settings` / `computer_control` — SO (críticos passam por owner_gate)
- `window_manager`, `open_app`, `browser_control`

**Memória e modo**
- `owner_setup`, `biometrics`, `agent_mode_control`
- `memory_compactor` (`consolidate`, `hygiene`, `forget_old`)
- `recall_memory` / save via tools de memória no core

**Código e shell**
- `code_forge`, `code_helper`, `dev_agent`, `code_review_local`
- `powershell_cmd`, `powershell_generator`

**Produtividade**
- `file_controller`, `file_organize`, `web_search`, `deep_research`
- `focus_timer`, `email_triage`, `meeting_brief`

Lista longa de actions adicionais em `actions/` e plugins em `plugins/` — cada arquivo com `TOOL` ou `PLUGIN` entra sozinho no próximo start (ou via `hot_reload`).

---

## Estrutura do projeto

```
jarvis_project/
├── main.py                 # sessão ao vivo, dispatch de tools
├── ui.py                   # HUD / avatar / confirmações
├── setup.py                # PONTE → requirements*.txt (+ browsers opcionais)
├── requirements.txt        # dependências do dia a dia
├── requirements-local.txt  # voz offline (STT/TTS/wake)
├── requirements-heavy.txt  # pandas, mcp, chromadb, mediapipe…
├── EXTENDING.md            # como criar actions/plugins
├── actions/                # tools (TOOL + handler)
├── plugins/                # plugins (PLUGIN + run)
├── core/                   # outcome, confirm, owner_gate, mcp, contracts…
├── memory/                 # long_term, episódios, grafo, biometrics/, audit/
├── providers/              # LLM / STT / TTS / engines (lazy)
├── config/                 # api_keys, agent_mode, mcp_servers.example…
├── scripts/                # new_module.py, check_deps.py
├── tests/
└── dashboard/              # painel no celular
```

---

## Requisitos e instalação

- Python **3.11–3.13** (recomendado 3.11/3.12)
- Windows, macOS ou Linux
- (Local) [Ollama](https://ollama.com) + `ollama pull qwen2.5-coder:7b`
- (Opcional) `ffmpeg` no PATH se for usar `vozdono.mp3`

### O que o `setup.py` instala?

| Comando | O que baixa |
|---------|-------------|
| `python setup.py` | **Só** `requirements.txt` |
| `python setup.py --local` | + `requirements-local.txt` |
| `python setup.py --heavy` | + `requirements-heavy.txt` |
| `python setup.py --browsers` | motores Playwright (chromium + firefox) — **pesado** |
| `python setup.py --all` | local + heavy + browsers |

**Não:** o setup padrão **não** instala os três arquivos de uma vez. Isso evita baixar centenas de MB (MCP, chromadb, mediapipe, browsers) em todo clone. Para “máquina completa de desenvolvimento”:

```bash
python setup.py --all
```

Para uso diário típico (app + voz local depois):

```bash
python setup.py
python setup.py --local          # quando for usar offline
ollama pull qwen2.5-coder:7b
python main.py
```

Equivalente manual:

```bash
pip install -r requirements.txt
pip install -r requirements-local.txt   # opcional
pip install -r requirements-heavy.txt   # opcional
python -m playwright install chromium firefox   # opcional
```

Checagem rápida de imports:

```bash
python scripts/check_deps.py
python tests/test_quality_layers.py
python tests/test_action_contracts.py
```

Coloque a chave Gemini em `config/api_keys.json` ou `.env` (`MARK_GEMINI_API_KEY` / `GEMINI_API_KEY`).

---

## Como estender

Guia curto: **`EXTENDING.md`**.

```bash
python scripts/new_module.py action minha_ferramenta --desc "Faz X" --risk safe
python scripts/new_module.py plugin meu_plugin --desc "…"
```

- Actions: módulo em `actions/` com `TOOL` + `handler`, retornando `done` / `failed` / `ask`…
- Plugins: `plugins/` com `PLUGIN` + `run(...)`
- Sem registrar em `main.py` — discovery automático
- Recarregar: `hot_reload action=actions` ou `action=one name=...`

Risk recomendado: declare `"risk": "safe"|"review"|"destructive"|"autonomous"` no `TOOL`.

---

## Dados e privacidade

- Memória e biometria ficam **só na sua máquina** (`memory/`)
- Biometria guarda **fingerprints**, não o áudio/foto por obrigação de runtime (os arquivos base `vozdono` / `fotobase*` são o cadastro que você controla)
- Logs de tools passam por **redaction** de secrets
- Ações críticas geram linhas em `memory/audit/`
- Modo **air_gapped** (`agent_mode_control`) bloqueia tools claramente de nuvem
- Nada de telemetria obrigatória do MARK LVI

---

## Ideias para o próximo passo

Sugestões de alto impacto, ainda não obrigatórias no código:

1. **Wizard de 1ª execução no HUD** — gravar comando + 3 fotos com preview, sem mexer em paths manuais
2. **Unlock no boot** — sessão começa em `listen` até voz ou face passarem
3. **Circuit breaker real** em `browser_control` / `desktop_agent` (já existe a API em `core/retry.py`)
4. **Indicador de modo** no avatar (cor/anel: listen / assist / autonomous / validating)
5. **Perfis multi-usuário** — vários `vozdono` + fotos por pessoa na mesma máquina
6. **Policy pack** — JSON de “o que o agente pode fazer sozinho” por horário/app
7. **Export/import de memória** criptografado (backup portátil)
8. **Bench local** — script que mede latência STT→LLM→TTS com o modelo Ollama atual
9. **Skill store leve** — um `plugins/marketplace` que só baixa `.py` assinado + deps declaradas
10. **Testes de regressão de outcome** por tool crítica (golden strings `status=`)

Se quiser priorizar uma dessas no próximo ciclo, diga qual.

---

## Licença e autoria

Ver `LICENSE` e `AUTORIA.md`.
