# MARK LVI (56)

### Assistente virtual e agente autônomo de desktop

Este repositório contém o código-fonte e a arquitetura do **MARK LVI (56)** (JARVIS), um ecossistema avançado de assistente virtual automatizado e agente autônomo baseado em inteligência artificial. O projeto está estruturado em módulos independentes e extensíveis que abrangem automação de desktop, processamento de linguagem natural (STT/TTS), monitoramento proativo do sistema, geração e correção de código, e integração com modelos de linguagem (LLMs) — em nuvem (Gemini Live) ou 100% locais (Ollama, LM Studio, Whisper, Piper, etc.).

O MARK LVI (56) ouve, vê, fala e controla o computador em **Windows, macOS e Linux**. Por padrão usa a API Gemini Live para voz em tempo real; se não houver cota, rede ou permissão para enviar áudio à nuvem, o mesmo avatar, memória, confirmações e actions continuam disponíveis com um motor local configurado em **⚙ → ENGINE & PROVIDERS**.

Não há servidor MARK LVI (56) na nuvem, telemetria obrigatória nem assinatura. O que você não usa (pasta `providers/`, wake word, dashboard no celular) **não é carregado** na inicialização.

---

## Índice

1. [Visão geral](#visão-geral)
2. [Tools unificadas (preferir estas)](#tools-unificadas-preferir-estas)
3. [Estrutura do projeto](#estrutura-do-projeto)
4. [Requisitos e instalação](#requisitos-e-instalação)
5. [Como estender o MARK LVI (56)](#como-estender-o-mark-lvi-56)
6. [Dados e privacidade](#dados-e-privacidade)
7. [Licença e autoria](#licença-e-autoria)

---

## Visão geral

| Capacidade | Descrição |
|---|---|
| Voz em tempo real | Conversa contínua via Gemini Live ou pipeline local (STT → LLM → TTS) |
| Avatar holográfico | Cabeça 3D no HUD, lip-sync e expressão — renderização em software, sem GPU obrigatória |
| Wake word | “Hey Jarvis” / “Mark LVI” local e opcional (baixo consumo, sem stream enquanto dorme) |
| Memória | Preferências e fatos em `memory/long_term.json`, com busca sob demanda |
| Undo e confirmação | Reversão de ações e gate de HUD para operações irreversíveis (o modelo **não** pode forjar o “sim”) |
| Outcomes honestos | Tools respondem `done` / `unverified` / `failed` / `ask` / `started` com base no que foi **observado** |
| Actions e plugins | Cada arquivo em `actions/` ou `plugins/` declara um `TOOL` e é descoberto automaticamente |
| Dashboard no celular | Painel local (`dashboard/`) com pareamento por QR |

---

## Tools unificadas (preferir estas)

Para o modelo e para quem desenvolve skills, estas três entradas cobrem vários módulos internos. Use-as em vez de chamar quatro tools parecidas.

| Tool | Substitui / cobre | Uso típico |
|---|---|---|
| **`code_assist`** | `code_forge`, `code_helper`, `dev_agent`, `code_review_local` | Gerar Python e **autocorrigir** erros detectados; editar/rodar código; scaffold de projeto multi-arquivo; review git (status/diff) |
| **`powershell_assist`** | `powershell_cmd`, `powershell_generator` | Comando curto **ou** pedido em linguagem natural → script `.ps1` (backup, zip, limpeza…), com varredura de perigo e confirmação |
| **`game_assist`** | `network_guard`, `game_coach`, `game_player` | Sessão “ranked”: alertas de latência de rede + coach de dicas; dino do Chrome / hold de teclas offline — **sem** aimbot nem ESP de inimigos |

### Outras actions recentes de desempenho e manutenção

| Action | Função |
|---|---|
| `resource_governor` | Reduz carga do MARK LVI (56) sob CPU/RAM alta ou bateria baixa |
| `memory_compactor` | Compacta `long_term.json`, backup e garbage collection |
| `hot_reload` | Recarrega actions/plugins sem reiniciar o app |
| `dependency_health` | Verifica pacotes críticos e sugere `pip install` |
| `audio_latency_tuner` | Mede e grava buffer de áudio preferido |
| `action_analytics` | Uso, falhas e tempo médio das actions |

---

## Estrutura do projeto

### 1. `actions/` — Automação e assistência

Módulos que executam tarefas do sistema e do usuário. Cada arquivo expõe um dicionário `TOOL` (`name`, `description`, `parameters`, `handler`).

**Entradas unificadas (preferenciais)**

* **`code_assist.py`**: ponte única para código (forge + helper + projeto + git).
* **`powershell_assist.py`**: shell/PowerShell unificado (comando curto ou gerador de scripts).
* **`game_assist.py`**: rede + coach + player simples em uma sessão.

**Código e desenvolvimento**

* **`code_forge.py`**: gera Python, analisa (AST/`py_compile`), executa e corrige em loop os erros que ele mesmo identifica.
* **`code_helper.py`**: write / edit / explain / run / build / optimize (multi-linguagem).
* **`dev_agent.py`**: agente de projeto multi-arquivo (plano, arquivos, deps, execução).
* **`code_review_local.py`**: status, branch e diff do git local (fatos para a IA redigir o review).
* **`self_program.py`**: utilitários de auto-programação / inspeção de módulos.

**Shell e sistema**

* **`powershell_cmd.py`**: execução segura de comandos (allowlist + `force`).
* **`powershell_generator.py`**: linguagem natural → `.ps1` → validação → execução (com `confirm.py`).
* **`computer_control.py`** & **`computer_settings.py`**: teclado, mouse, atalhos e configurações do SO.
* **`process_manager.py`**: listar, priorizar e encerrar processos.
* **`system_health.py`**, **`system_monitor.py`**, **`background_monitor.py`**: saúde e monitoramento contínuo.
* **`resource_governor.py`**: governança de recursos do próprio assistente.
* **`dependency_health.py`**: integridade das dependências Python.
* **`network_status.py`** & **`network_guard.py`**: conectividade e alertas de latência.
* **`battery.py`**: carga e estado da bateria.
* **`open_app.py`**, **`desktop.py`**, **`window_manager.py`**: apps e janelas.

**Arquivos, web e produtividade**

* **`file_controller.py`**, **`file_organize.py`**, **`file_processor.py`**: criar, ler, organizar e processar arquivos.
* **`browser_control.py`**: automação de navegador (Playwright).
* **`web_search.py`**, **`deep_research.py`**: busca e pesquisa aprofundada.
* **`clipboard.py`** & **`clipboard_smart.py`**: área de transferência com contexto.
* **`email_triage.py`**, **`meeting_brief.py`**, **`quick_note.py`**, **`reminder.py`**.
* **`focus_timer.py`** & **`timer.py`**: Pomodoro e alarmes.
* **`unit_convert.py`**, **`flight_finder.py`**, **`bank_statement.py`**.
* **`weather_report.py`**, **`send_message.py`**.

**Mídia, tela e jogos**

* **`screen_processor.py`** & **`screenshot_ocr.py`**: captura e OCR.
* **`media_control.py`**, **`video_player.py`**, **`youtube_video.py`**.
* **`game_helper.py`**, **`game_updater.py`**, **`game_coach.py`**, **`game_player.py`**.

**Manutenção do próprio MARK LVI (56)**

* **`hot_reload.py`**, **`memory_compactor.py`**, **`action_analytics.py`**, **`audio_latency_tuner.py`**.
* **`ai_collaboration.py`**, **`proactive.py`**.

---

### 2. `core/` — Núcleo do MARK LVI (56)

Motor que orquestra inteligência, interface lógica e pipelines:

* **`action_loader.py`** & **`action_feedback.py`**: descoberta e validação de actions.
* **`plugin_loader.py`**: carregamento de `plugins/`.
* **`outcome.py`**: protocolo `done` / `unverified` / `failed` / `ask` / `started`.
* **`confirm.py`**: confirmação na HUD (token emitido pela interface, não pelo modelo).
* **`undo.py`**: pilha de desfazer compartilhada.
* **`appidentity.py`**: identidade de apps e proteção dos processos do próprio assistente.
* **`audio_devices.py`**: microfones e saídas.
* **`avatar.py`**, **`avatar_mesh.py`**, **`face_model.obj`**, **`viseme.py`**, **`echo.py`**: avatar, lip-sync e anti-eco.
* **`gemini.py`** & **`llm_client.py`**: Gemini e LLMs locais/compatíveis OpenAI.
* **`stt.py`** & **`tts.py`**: reconhecimento e síntese de voz.
* **`wake_word.py`**: ativação por voz local.
* **`hotkey.py`**: atalhos (ex.: push-to-talk).
* **`lazyimport.py`**: imports pesados só no primeiro uso.
* **`offline_assistant.py`**: caminho degradado offline.
* **`platform_support.py`**: o que o SO realmente permite (ex.: limites do Wayland).
* **`installer.py`**: apoio a dependências/binários.
* **`prompt.txt`**: personalidade e regras base do MARK LVI (56).

---

### 3. `dashboard/` e `config/` — Interface e configurações

* **`dashboard/server.py`** & **`dashboard/static/`** (`app.html`, `login.html`, `crypto-js.min.js`): painel web local do MARK LVI (56), com autenticação.
* **`config/api_keys.json`**: credenciais (Gemini, ElevenLabs, provedores, etc.) — **texto local, trate como senha**.
* **`config/autostart_state.json`**: preferência de iniciar com o SO.
* **`config/certs/`**: certificado TLS local do dashboard (quando HTTPS).
* Ícones `jarvis.ico` / `jarvis_icon_*.png` para tray e janelas.

---

### 4. `memory/` — Memória e contexto

* **`memory_manager.py`** & **`config_manager.py`**: persistência e preferências de runtime.
* **`long_term.json`**: identidade, preferências, projetos, relações, notas e índice de sessões.

---

### 5. `plugins/` — Extensões modulares

* **`baixar_arquivo.py`**, **`clima.py`**, **`cotacao_dolar.py`**, **`noticias_brasil.py`**, **`resumo_link.py`**.
* **`whatsapp_web.py`**, **`desktop_agent.py`**, **`system_resources_monitor.py`**.
* **`modo_treinador.py`** & **`treinador_base/`**: metodologias e material de treino (ex.: futebol sub-13).
* **`programador.py`**, **`treino_hoje.py`**, **`weather_report.py`**.
* **`pending/`**: integrações em desenvolvimento (ex.: `hwmonitor_integration.py`).
* **`_template.py`**: modelo para novos plugins.

---

### 6. `providers/` — Motores de entrada/saída (opcional)

Só é importado quando você escolhe um engine diferente do Gemini Live padrão.

* **`engine_pipeline.py`**: áudio → STT → LLM → TTS → áudio.
* **`audio.py`**, **`base.py`**, **`registry.py`**, **`schema.py`**.
* **`stt_whisper.py`**, **`llm_openai.py`**.
* **`tts_elevenlabs.py`**, **`tts_piper.py`**, **`tts_system.py`**.

---

### 7. Raiz e suporte

* **`main.py`**: ponto de entrada do MARK LVI (56) — providers, núcleo, memória, sessão e HUD.
* **`ui.py`**: janela nativa / bandeja do sistema.
* **`setup.py`**: instalação de dependências conforme o SO.
* **`prepare_offline.py`**: download de pesos/modelos para uso offline.
* **`requirements.txt`** & **`requirements-local.txt`**.
* **`cache/`**: scripts PowerShell gerados, código forjado, artefatos temporários.
* **`tests/test_action_contracts.py`**: contrato mínimo das actions (`TOOL` + handler).
* **`AUTORIA.md`**, **`LICENSE`**.

---

## Requisitos e instalação

| Item | Detalhe |
|---|---|
| SO | Windows 10/11, macOS ou Linux |
| Python | 3.11, 3.12 ou 3.13 |
| Linux | Funcionalidade completa de GUI automation em **X11**. Em **Wayland**, digitação/clique/captura de tela de outros apps ficam limitados pelo SO; voz, memória, arquivos e web seguem normais |
| macOS | Acessibilidade e Gravação de tela em Privacidade e Segurança, se for controlar o desktop |
| Microfone / alto-falante | Necessários para voz |
| GPU | **Não obrigatória** |
| Chave API | Gemini na primeira execução (`config/api_keys.json`), **ou** motor 100% local sem chave |

### Instalação online

```bash
git clone <url-do-repositorio>
cd Mark-LVI   # ou o nome da pasta do MARK LVI (56)

python setup.py
# ou: pip install -r requirements.txt

python main.py
```

### Preparação offline

```bash
python prepare_offline.py
pip install -r requirements-local.txt
python main.py
```

Na primeira execução: informe a chave Gemini **ou** configure STT/LLM/TTS locais em **⚙ → ENGINE & PROVIDERS**. Wake word é opcional em **⚙ → WAKE WORD**.

---

## Como estender o MARK LVI (56)

1. Crie um arquivo em `actions/` (ou `plugins/` para pacotes opcionais).
2. Exporte um `TOOL` com `name`, `description`, `parameters` e `handler`.
3. Prefira retornos de `core.outcome` (`done`, `failed`, `ask`, …) com **fatos**, não prosa longa.
4. Reinicie o app ou use a action **`hot_reload`**.

Testes de contrato: `tests/test_action_contracts.py`.

---

## Dados e privacidade

Tudo permanece na sua máquina. Não há conta MARK LVI (56) nem telemetria embutida obrigatória.

| O quê | Onde | Nota |
|---|---|---|
| **Segredos (recomendado)** | `.env` na raiz do projeto | Variáveis `MARK_GEMINI_API_KEY`, etc. — **nunca** versionar. Modelo: `.env.example` |
| Ajustes de UI / engine | `config/api_keys.json` | Preferências, voz, devices. Modelo sem segredos: `config/api_keys.json.example` |
| Certificado do dashboard | `config/certs/` | Gerado localmente |
| Memória | `memory/long_term.json` | Apague o arquivo para o assistente “esquecer” |

### Chaves de API — ordem de prioridade

1. Variáveis de ambiente do sistema  
2. Arquivo **`.env`** (carregado via `python-dotenv`, se instalado)  
3. Campo correspondente em **`config/api_keys.json`**

Assim o desenvolvedor pode manter só preferências no JSON e as senhas no `.env`. Confiar apenas no `.gitignore` para `api_keys.json` ainda permite vazamento se alguém forçar o add do arquivo; o padrão `.env` + exemplos no repositório reduz esse risco.

```bash
cp .env.example .env
# edite .env e preencha MARK_GEMINI_API_KEY=...

cp config/api_keys.json.example config/api_keys.json   # opcional, para UI
```

`.env`, `config/api_keys.json` e `config/certs/` estão no `.gitignore`. Com **Gemini Live**, o áudio da sessão vai para a API Google enquanto a conversa estiver aberta. Com **engine local**, áudio e texto podem permanecer só no seu PC.

---

## Licença e autoria

* **Nome do aplicativo / assistente padrão:** MARK LVI (56)
* **Autoria:** consulte `AUTORIA.md`
* **Licença:** ver `LICENSE` (uso pessoal e não comercial — Creative Commons BY-NC 4.0, conforme o arquivo do repositório)

---

**MARK LVI (56)** — assistente de voz e agente de desktop, extensível por design.
