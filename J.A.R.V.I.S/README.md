# J.A.R.V.I.S. — MARK LXI

Documentação unificada do projeto.

## Índice

1. [ARCHITECTURE_F1_F2.md](#architecture-f1-f2-md)
2. [ARCHITECTURE_F3_F5.md](#architecture-f3-f5-md)
3. [AUTORIA.md](#autoria-md)
4. [config/certs/README.md](#config-certs-readme-md)
5. [config/roblox_assets/README.md](#config-roblox-assets-readme-md)
6. [docs_OWNER_BIOMETRICS.md](#docs-owner-biometrics-md)
7. [EXTENDING.md](#extending-md)
8. [memory/knowledge_docs/manual_jarvis_mark_lxi.md](#memory-knowledge-docs-manual-jarvis-mark-lxi-md)
9. [memory/knowledge_docs/manutencao_honda_city_e_casa.md](#memory-knowledge-docs-manutencao-honda-city-e-casa-md)
10. [memory/knowledge_docs/protocolos_emergencia_residencial.md](#memory-knowledge-docs-protocolos-emergencia-residencial-md)
11. [memory/knowledge_docs/saude_nutricao_basica.md](#memory-knowledge-docs-saude-nutricao-basica-md)
12. [memory/knowledge_docs/seguranca_cibernetica_rede_local.md](#memory-knowledge-docs-seguranca-cibernetica-rede-local-md)
13. [NEW_ACTIONS.md](#new-actions-md)
14. [readme.md](#readme-md)
15. [UPGRADE_4_FEATURES.md](#upgrade-4-features-md)
16. [UPGRADE_QUALITY_LAYERS.md](#upgrade-quality-layers-md)

---

## ARCHITECTURE_F1_F2.md

<a id="architecture-f1-f2-md"></a>

# MARK LXI — Mapa de Arquitetura (Frentes 1 e 2)

```
                    ┌─────────────────────────────┐
                    │  main.py / action_loader    │
                    │  plugin_loader / hot_reload │
                    └─────────────┬───────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ actions/code_*   │   │ plugins/*_assist │   │ core/outcome     │
│ (wrappers)       │   │ roblox/blender/  │   │ contracts/retry  │
└────────┬─────────┘   │ godot            │   └──────────────────┘
         │             └────────┬─────────┘
         ▼                      ▼
┌──────────────────┐   ┌──────────────────┐
│ core/code_engine │   │ core/engine_     │
│ Architect        │   │ bridge           │
│ Builder          │   │  ├─ roblox_bridge│
│ SandboxVerifier  │   │  ├─ blender CLI  │
│ AutoHealer       │   │  └─ godot files  │
└────────┬─────────┘   └────────┬─────────┘
         │                      │
         ▼                      ▼
┌──────────────────┐   ┌──────────────────┐
│ core/sandbox     │   │ Studio plugin    │
│ core/retry       │   │ .rbxmx / FBX     │
│ LLM (gemini/     │   │ project.godot    │
│  llm_client)     │   │                  │
└──────────────────┘   └──────────────────┘
```

## Frente 1 — Programação unificada

| Legado | Destino |
|--------|---------|
| `code_forge` | `CodeEngine.forge / generate / analyze / fix` |
| `code_helper` | `generate_python / builder / run_module` |
| `code_assist` | `pipeline()` |
| `code_review_local` | `analyze` + git facts |
| `dev_agent` | `pipeline()` multi-file |
| `self_program` | `analyze` + `builder` (write gated) |

## Frente 2 — Bridge 3D

| Target | Transporte |
|--------|------------|
| Roblox | `roblox_bridge` HTTP `:28859` + Luau plugin + `.rbxmx` |
| Blender | `blender --background --python` via `engine_bridge` |
| Godot | escrita de `project.godot` / `.gd` / `.tscn` |

`dispatch({"target":"roblox|blender|godot", "type":"..."})` é a API única.


---

## ARCHITECTURE_F3_F5.md

<a id="architecture-f3-f5-md"></a>

# Frentes 3–5 — o que mudou

## Frente 3 — Segurança
- `core/static_safety.py` — AST Python + blocklist shell
- `actions/powershell_cmd.py` — static_safety → confirm → owner_gate → exec
- `actions/self_program.py` — analyze_python(strict) + owner_gate antes de write
- `dashboard/server.py` — middleware Origin, headers, CSRF opcional (`/api/csrf`, `X-CSRF-Token`), `/ws/telemetry`

## Frente 4 — Latência e memória
- `providers/engine_pipeline.py` — `_take_sentences` libera cláusulas cedo (TTFA)
- `memory/entity_index.py` — índice em memória de entidades
- `actions/memory_compactor.py` — `lookup` + rebuild no consolidate

## Frente 5 — Higiene
- Plugins promovidos de `pending/`
- `HYGIENE_OBSOLETE.md`
- Type hints / outcome nos módulos tocados
- Testes de contrato devem continuar passando


---

## AUTORIA.md

<a id="autoria-md"></a>

# Autoria — J.A.R.V.I.S. MARK LXI (61)

| Campo | Valor |
|-------|--------|
| **Nome do aplicativo** | J.A.R.V.I.S. — MARK LXI (61) |
| **Assistente padrão** | J.A.R.V.I.S. |
| **Autor** | Guilherme |
| **Ano** | 2026 |
| **Licença** | [CC BY-NC 4.0](LICENSE) |

## Escopo desta build

Assistente de desktop **offline-first** com operação 24/7, biometria sequencial (face → voz, threshold **0.75**), protocolos de segurança (190 silencioso, demo, dissuasão), vigilância iCSee, casa inteligente, finanças por voz, administração remota e **Telegram** (texto + **mensagens de voz**) com alternância de canal de áudio casa / rua / híbrido.

## Wake words (legado / UI)

A escuta padrão é **contínua** (sem palavra obrigatória). Referências históricas de ativação: `Jarvis`, `J.A.R.V.I.S.`, `Mark LXI`, `Hey Jarvis`.

## Contato de autoria

Reservados todos os direitos não concedidos pela CC BY-NC 4.0. Uso comercial não autorizado.


---

## config/certs/README.md

<a id="config-certs-readme-md"></a>

# Generated at runtime by dashboard/server.py (_ensure_certs).
# Never commit jarvis.key or jarvis.crt — they are machine-specific.


---

## config/roblox_assets/README.md

<a id="config-roblox-assets-readme-md"></a>

# Roblox Studio Bridge (JARVIS)

## Instalar o plugin Luau

1. Abra a pasta de plugins do Studio:
   - Windows: `%LOCALAPPDATA%\Roblox\Plugins`
   - macOS: `~/Documents/Roblox/Plugins` (ou via Studio → Plugins → Plugins Folder)
2. Copie `studio_bridge_plugin.lua` para essa pasta (renomeie se quiser).
3. Reinicie o Roblox Studio.
4. No JARVIS: `roblox_assist action=bridge_start`
5. No Studio, clique **Connect** na toolbar **JARVIS Bridge**.
6. HttpService precisa permitir pedidos locais (em jogo/plugin conforme politica do Studio).

## Fluxo de modelagem

```text
roblox_assist action=bridge_start
roblox_assist action=build_live structure=house width=30 height=14
roblox_assist action=export_rbxmx structure=tower floors=4 output=~/RobloxProjects/t.rbxmx
roblox_assist action=blender_mesh name=PropA prompt="low poly crate" format=fbx
```


---

## docs_OWNER_BIOMETRICS.md

<a id="docs-owner-biometrics-md"></a>

# Cadastro do dono e ações críticas

## Primeira inicialização

Se faltar qualquer um destes arquivos em `memory/biometrics/`, o JARVIS considera o cadastro incompleto:

| Arquivo | Conteúdo |
|---------|----------|
| `vozdono.mp3` | Sua voz dizendo o comando (ex.: “ok jarvis”, “acorda jarvis”) |
| `fotobase1.jpg` | Rosto de **frente** |
| `fotobase2.jpg` | Rosto de **um lado** |
| `fotobase3.jpg` | Rosto do **outro lado** |
| `owner_command.json` | Frase escolhida (`{"phrase": "ok jarvis"}`) |

Na subida, o terminal/HUD avisa o que falta.

### Via tool

```text
owner_setup action=set_phrase phrase="ok jarvis"
owner_setup action=enroll_voice path=/caminho/sua_gravacao.wav
owner_setup action=enroll_face slot=1 image_path=/fotos/frente.jpg
owner_setup action=enroll_face slot=2 image_path=/fotos/lado_a.jpg
owner_setup action=enroll_face slot=3 image_path=/fotos/lado_b.jpg
owner_setup action=status
```

Webcam (se OpenCV + câmera):

```text
owner_setup action=enroll_face slot=1 camera=true
```

Você também pode **copiar** os arquivos prontos para `memory/biometrics/` com esses nomes; na próxima verificação a tool reconstrói o perfil.

## Ações críticas (shutdown / restart / reset)

Fluxo:

1. Biometria do dono — **voz OU câmera/foto** (não precisa dos dois)
2. Banner CONFIRM no HUD (como antes)
3. Só então executa

Exemplos:

```text
computer_settings action=shutdown owner_voice_path=/tmp/probe.wav
computer_settings action=restart owner_camera=true
computer_settings action=shutdown owner_image_path=/tmp/selfie.jpg
```

Sem biometria a tool responde `status=ask` e **não desliga nada**.

## Dependências

- Voz: `numpy` (+ `ffmpeg` no PATH se o áudio for MP3)
- Face: `opencv-python` (4.x) e/ou `face_recognition`
- Confirmação na tela: UI ligada (`core.confirm`)


---

## EXTENDING.md

<a id="extending-md"></a>

# Estendendo o J.A.R.V.I.S. / MARK LXI

Tudo novo encaixa em **actions/** (tools descobertas pelo `action_loader`) ou
**plugins/** (descobertos pelo `plugin_loader`). Não precisa registrar em
`main.py`.

## Setup (só ponte)

```bash
python setup.py              # requirements.txt
python setup.py --local      # + voz offline
python setup.py --heavy      # + pandas/mcp/chroma/…
python setup.py --browsers   # motores Playwright
python setup.py --all
```

Edite `requirements.txt` / `requirements-local.txt` / `requirements-heavy.txt`.
O `setup.py` não lista pacotes — só chama o pip nesses arquivos.

## Criar action ou plugin em 10 segundos

```bash
python scripts/new_module.py action minha_ferramenta --desc "Faz X quando o usuário pedir Y" --risk safe
python scripts/new_module.py plugin meu_plugin --desc "…"
```

### Contrato de action (`actions/*.py`)

```python
TOOL = {
    "name": "minha_ferramenta",
    "description": "…",          # o modelo lê isto
    "parameters": {"type": "OBJECT", "properties": {...}, "required": []},
    "handler": minha_ferramenta, # callable
    "risk": "safe",              # safe | review | destructive | autonomous
}
```

Sempre devolver strings do `core.outcome`:

```python
from core.outcome import done, failed, ask, unverified, started
return done("minha_ferramenta", note="ok")
```

### Contrato de plugin (`plugins/*.py`)

```python
PLUGIN = { "name": "...", "description": "...", "parameters": {...} }

def run(parameters, player=None, session_memory=None) -> str:
    return "status=done action=... result=..."
```

## Camadas úteis ao estender

| Módulo | Quando usar |
|--------|-------------|
| `core.outcome` | Resposta honesta ao modelo |
| `core.contracts` | risk tiers / validação de schema |
| `core.confirm` | Ação irreversível com banner no HUD |
| `core.owner_gate` | Shutdown/restart → biometria do dono |
| `core.sandbox` | dry-run / paths seguros |
| `core.redaction` | Logs sem vazar secrets |
| `core.audit` | Trilha de ações críticas |
| `core.agent_mode` | listen / assist / autonomous |
| `core.retry` | Rede/UI instável |
| `memory.memory_manager` | Fatos, episódios, grafo |

## Hot reload

Sem reiniciar o processo:

```text
hot_reload action=actions
hot_reload action=one name=minha_ferramenta
```

## Testes mínimos

```bash
python tests/test_action_contracts.py
python tests/test_quality_layers.py
python scripts/check_deps.py
```

## Biometria do dono

Ver `docs_OWNER_BIOMETRICS.md`. Arquivos em `memory/biometrics/`.

## Modelo local padrão

Ollama: `qwen2.5-coder:7b` (`config/api_keys.json` / `core/llm_client.py`).

## Plugins de apps criativos (exemplos inclusos)

| Plugin | App | O que faz |
|--------|-----|-----------|
|  | Blender | abrir, mesh básico, script bpy, export, render |
|  | Roblox Studio + Rojo | projeto Rojo, scripts Luau, abrir Studio |
|  | Godot | projeto, GDScript, abrir editor |

Variáveis de ambiente úteis: , , .


---

## memory/knowledge_docs/manual_jarvis_mark_lxi.md

<a id="memory-knowledge-docs-manual-jarvis-mark-lxi-md"></a>

# Manual Técnico J.A.R.V.I.S. — MARK LXI (61)

## Identidade
Assistente de desktop multiplataforma (Windows/Linux/macOS), offline-first, autoria Guilherme, licença CC BY-NC 4.0.

## Arquitetura
- `main.py`: entrypoint 24/7, boot, workers daemon.
- `actions/`: tools públicas com `TOOL` + `handler`; implementações em `_impl.py`.
- `core/`: event_bus, outcome, contracts, resilience, audit, knowledge_store, continuous_listen.
- `providers/`: STT Whisper, TTS Piper/system, engine_pipeline.
- `memory/`: long_term, episodes, audit, knowledge_base.db, biometrics/familia.
- `dashboard/`: FastAPI + HUD web (SSE eventos, ROI editor).

## Actions principais (seleção)
- **protocolo** 190/demo — emergência silenciosa multi-canal.
- **sentinel_patrol** — ronda, modo ausente/encomenda.
- **leitor_placas_alpr** — placa ABC1D23 Veículo Exemplo como veículo confiável.
- **porteiro inteligente** — desconhecido >15s + botões Telegram.
- **offline** — bunker: Ollama + bloqueio de nuvem.
- **mover_downloads** — recorta de Downloads para raiz/actions/core.
- **mission_planner** — cadeias multi-tool.
- **telegram_commander** — /190 /cameras /status /offline /mcp.
- **daily_ops** — briefing matinal + finanças.
- **diario_cognitivo** — retrospectiva semanal falada.
- **lista_compras / cacador_ofertas** — ofertas ≥10% abaixo da média.
- **smart_climate** — pré-climatização na chegada do Veículo Exemplo se T>27°C ou T<16°C.

## Contratos
Todo handler retorna `done` / `failed` / `ask` de `core.outcome`. Subprocessos com `timeout=`. Imports pesados lazy.

## Segurança
- Senha mestra padrão configurável: `JARVIS_MASTER_PASSWORD` (default legado de testes: 123jarvis834).
- Protocolo 190 **nunca** pede senha.
- Modo viagem exige senha para abrir portão.
- `core/redaction.py` mascara tokens em logs.

## EventBus
Pub/Sub + regras em `config/event_rules.json` com cooldown, AND composto, ações tipadas (telegram, offline, smart_home, sentinel, etc.).

## RAG local
`core/knowledge_store.py` indexa `memory/knowledge_docs/` em SQLite FTS5 + BM25 puro. Consultar via `local_doc_rag` ou modo offline.


---

## memory/knowledge_docs/manutencao_honda_city_e_casa.md

<a id="memory-knowledge-docs-manutencao-honda-city-e-casa-md"></a>

# Manutenção Preventiva — Veículo Exemplo e Residência

## Veículo Exemplo (placa de referência ABC1D23)
### Intervalos típicos (consultar manual do ano do veículo)
- Óleo e filtro: a cada 10.000 km ou 12 meses (o que ocorrer primeiro).
- Filtro de ar: 20.000 km; cabine/ar-condicionado: 15.000–20.000 km.
- Velas: conforme especificação (geralmente 40.000–60.000 km em ignição).
- Fluido de freio: substituição a cada 24 meses.
- Pneus: calibragem mensal a frio; rodízio a cada 10.000 km; sulco mínimo legal 1,6 mm.

### Checklist semanal
- Luzes (freio, seta, farol), buzina, limpadores.
- Vazamentos sob o motor após estacionar.
- Pressão do estepe e macaco.

### Integração J.A.R.V.I.S.
- ALPR reconhece ABC1D23 como confiável → eventos noturnos (luz garagem/portão) e pré-climatização.
- Cadastrar outras placas em `config/known_vehicles.json` ou por voz no `leitor_placas_alpr`.

## Residência — preventivo
- Testar disjuntores DR mensalmente.
- Limpar filtros de ar-condicionado a cada 30–60 dias (clima de Rio Preto é quente e seco em grande parte do ano).
- Verificar vedação de portas/janelas antes da temporada de chuvas.
- Câmeras iCSee: confirmar gravação e horário NTP; ROI/tripwire no muro e portão.
- Backup: `backup_nuvem` / retenção de evidências >7 dias limpa automaticamente (exceto 190).

## Rede local
- Separar IoT em VLAN quando possível.
- Trocar senha Wi-Fi periodicamente; radar_dispositivos_wifi alerta novos MACs.
- AudioRelay: iniciado no boot do main se instalado.


---

## memory/knowledge_docs/protocolos_emergencia_residencial.md

<a id="memory-knowledge-docs-protocolos-emergencia-residencial-md"></a>

# Protocolos de Emergência Residencial — Cidade Exemplo

## Contatos críticos
- Polícia Militar: **190**
- Bombeiros: **193**
- SAMU: **192**
- Defesa Civil municipal: 0800 / canais oficiais da prefeitura
- Endereço de referência do sistema: Rua Exemplo, nº 00, nº 244, Jardim Europa, Cidade Exemplo - SP

## Protocolo 190 (J.A.R.V.I.S.)
1. Execução **imediata e silenciosa** (sem TTS alto, sem senha).
2. Abrir/focar o app de câmeras **iCSee**.
3. Capturar evidência (screenshot/ROI) e analisar visão.
4. Enviar foto + mensagem de socorro via WhatsApp/Telegram ao contato de confiança (`EMERGENCY_CONTACT_PHONE`).
5. Mensagem padrão inclui endereço completo e resumo visual das câmeras.
6. Nunca discar 190 automaticamente pelo PC; o pedido é para o contato humano ligar.

## Incêndio
1. Evacuar pessoas e animais; não usar elevador se houver.
2. Fechar portas ao sair para retardar propagação.
3. Acionar 193; informar endereço e se há pessoas presas.
4. Se o fogo for pequeno e controlável: extintor adequado (não use água em eletrodomésticos energizados).
5. Desligar disjuntor geral somente se o caminho estiver seguro.

## Invasão / suspeita de arrombamento
1. Não confrontar. Preferir evidência e alerta remoto.
2. Ativar protocolo 190 ou modo dissuasão (luzes + áudio) conforme risco.
3. Registrar evidências em `memory/audit/evidencias/`.
4. Tripwires configurados no muro/portão distinguem invasão de passagem na calçada.

## Queda de energia prolongada
1. Self-healing monitora transição AC→DC (bateria).
2. Em modo viagem: priorizar alertas Telegram e reduzir carga do PC (eco profile).
3. Verificar nobreak e temperatura de servidores locais (Ollama).

## Primeiros socorros básicos
- **Engasgo adulto:** manobra de Heimlich; se inconsciente, RCP e 192.
- **Queimadura superficial:** água corrente fria por 10–20 min; não aplicar pasta/creme caseiro.
- **Hemorragia:** pressão direta com pano limpo; elevar o membro se possível.
- **Choque elétrico:** desligar a fonte antes de tocar na vítima.


---

## memory/knowledge_docs/saude_nutricao_basica.md

<a id="memory-knowledge-docs-saude-nutricao-basica-md"></a>

# Saúde e Nutrição — Referência Rápida (não substitui orientação médica)

## Hidratação e calor (interior paulista)
- Em dias >32°C, aumentar ingestão de água; evitar esforço no pico de calor.
- Sinais de insolação: confusão, pele quente e seca, náusea → sombra, resfriamento, 192 se grave.

## Sono
- Janela pré-sono do J.A.R.V.I.S. (config `smart_climate.json`) pode preparar ambiente 20 min antes do horário habitual.
- Higiene de sono: luz baixa, evitar cafeína após 16h para sensíveis.

## Alimentação geral
- Priorizar refeições com proteína + fibra + hortaliças.
- Delivery frequente: o auditor financeiro alerta se a categoria delivery superar ~15% acima da média semanal histórica.

## Farmácia doméstica mínima
- Analgésico/antitérmico conforme orientação prévia do médico.
- Soro de reidratação, antisséptico, gazes, termômetro.
- Verificar validade a cada 6 meses.

## Quando procurar emergência
- Dor no peito, falta de ar intensa, AVC (FAST), sangramento que não cessa, perda de consciência → 192.


---

## memory/knowledge_docs/seguranca_cibernetica_rede_local.md

<a id="memory-knowledge-docs-seguranca-cibernetica-rede-local-md"></a>

# Segurança Cibernética e Rede Local

## Princípios
1. Menor privilégio: actions destrutivas passam por `owner_gate` / confirmação (exceto 190).
2. Segredos em `.env` / vault; nunca em commits; `redaction` em logs.
3. Offline mode bloqueia APIs externas e mantém LAN (câmeras, Tuya local, AudioRelay).

## Hardening Windows 24/7
- `powercfg` evita sleep na tomada (script install_24h).
- Watchdog reinicia `main.py` se o processo cair.
- Self-healing: RTSP, Ollama `:11434`, polling Telegram.

## Rede
- Preferir WPA2/WPA3; desativar WPS.
- Inventário de MACs em `memory/dispositivos_conhecidos.json`.
- Eventos `wifi.device_joined` / `wifi.device_left` alimentam modo viagem (>6h sem residentes).

## Dashboard
- Bind preferencial a localhost; autenticação de sessão nas rotas.
- SSE `/api/events/stream` para telemetria; não expor sem túnel autenticado.

## Backup e recuperação
- `memory/` é o núcleo de estado; evidências antigas são podadas.
- Testes: `pytest -q tests/` deve permanecer verde após mudanças.


---

## NEW_ACTIONS.md

<a id="new-actions-md"></a>

# Novas actions — MARK LXI

## Implementadas neste pacote

| Action | Arquivo | O que faz |
|--------|---------|-----------|
| `network_status` | `actions/network_status.py` | Hostname, IP local, IP público, se há internet |
| `unit_convert` | `actions/unit_convert.py` | Converte comprimento, massa, temperatura, volume, velocidade, dados |
| `quick_note` | `actions/quick_note.py` | Notas em `~/.jarvis/notes/*.md` (+ opcional memória de longo prazo) |

São descobertas automaticamente pelo `core.action_loader` (dict `TOOL` + handler).


## Implementadas a pedido (extrato / OCR / games)

| Action | Arquivo | O que faz |
|--------|---------|-----------|
| `bank_statement` | `actions/bank_statement.py` | Analisa extrato CSV/OFX/texto/PDF: categorias, economia, reserva/investir (educativo) |
| `screenshot_ocr` | `actions/screenshot_ocr.py` | Print da tela ou imagem → texto (Tesseract local ou Gemini vision) |
| `game_helper` | `actions/game_helper.py` | Coach de games: tips, counter, build, checklist, lookup |

## Ideias para as próximas

1. **`calendar_today`** — agenda do dia (Google Calendar OAuth ou `.ics` local).
2. **`pomodoro`** — ciclos 25/5 com notificação OS (complementa `focus_timer` / `timer`).
3. **`clipboard_history`** — últimas N entradas do clipboard (com cuidado de privacidade).
4. **`wifi_control`** — listar redes / status (Windows `netsh`, Linux `nmcli`).
5. **`screenshot_ocr`** — captura + OCR (Tesseract) para “o que está escrito na tela”.
6. **`expense_log`** — registrar gasto rápido em CSV/SQLite (“gastei 40 no almoço”).
7. **`git_status_summary`** — `git status` + diff resumido no repo atual.
8. **`translate_text`** — traduzir trecho (API ou modelo local pipeline).
9. **`volume_mixer`** — volume por app (Windows Core Audio / Pulse `pactl`).
10. **`smart_home_toggle`** — ligar/desligar dispositivo Tuya/MQTT (há deps opcionais no requirements).
11. **`meeting_join`** — abrir link Zoom/Meet a partir da agenda ou clipboard.
12. **`disk_hog`** — top pastas que mais ocupam espaço em um diretório.
13. **`speedtest_lite`** — estimativa de latência/download sem instalar speedtest-cli.
14. **`password_gen`** — gerar senha forte e (opcional) copiar para o clipboard.
15. **`read_aloud_selection`** — ler a seleção atual do SO / último clipboard.

Prioridade sugerida se o foco for produtividade diária: **calendar_today**, **git_status_summary**, **expense_log**, **screenshot_ocr**.


---

## readme.md

<a id="readme-md"></a>

# J.A.R.V.I.S. — MARK LXI (61)

Assistente de desktop **offline-first** (Windows / macOS / Linux) com voz contínua, biometria, autonomia 24/7 e controle remoto via **Telegram (texto + áudio)**.

**Autor:** Guilherme · **Licença:** [CC BY-NC 4.0](LICENSE) · **Autoria:** [AUTORIA.md](AUTORIA.md)

---

## Índice

1. [Visão geral](#visão-geral)
2. [Áudio: casa · rua · híbrido](#áudio-casa--rua--híbrido)
3. [Telegram (texto e voz)](#telegram-texto-e-voz)
4. [Protocolos e segurança](#protocolos-e-segurança)
5. [Actions 24/7](#actions-247)
6. [Instalação](#instalação)
7. [Modo 24/7 (Windows)](#modo-247-windows)
8. [Variáveis `.env`](#variáveis-env)
9. [Licença](#licença)

---

## Visão geral

| Área | Detalhe |
|------|---------|
| Voz | Escuta contínua (sem wake word obrigatória) |
| Biometria | Face → voz no boot (threshold **0.75**) |
| Nuvem | Gemini Live + fallback local (Ollama / Whisper / Piper) |
| Remoto | Bot Telegram: comandos `/` + **mensagens de voz** |
| Canal de áudio | `casa` · `telegram` (rua) · `hibrido` — persistido em `memory/audio_channel_state.json` |

---

## Áudio: casa · rua · híbrido

| Modo | Microfone local | Telegram | Comando |
|------|-----------------|----------|---------|
| **casa** | Ativo (+ AudioRelay se instalado) | Texto/voz OK | `/modo_casa` ou *“voltar áudio para a casa”* |
| **telegram** (rua) | Pausado | Exclusivo | `/modo_rua` ou *“modo rua”* |
| **hibrido** | Ativo | Ativo | `/audio_hibrido` |

Action: `audio_channel`. O estado sobrevive a reinícios 24/7.

**Regra:** `/190` ou áudio *“ativar protocolo 190”* no Telegram executa **sempre**, em silêncio na casa, mesmo em modo rua.

---

## Telegram (texto e voz)

1. Configure `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` no `.env`.
2. Inicie o JARVIS — o listener sobe no boot.
3. Envie texto **ou grave um áudio** no chat autorizado.

**Fluxo de voz:** download `.ogg` → conversão (`ffmpeg`/`pydub`) → STT (Whisper) → comando → resposta texto (+ `sendVoice` quando não for 190).

### Comandos `/` principais

`/cameras` `/status` `/falar` `/190` `/demo`  
`/modo_rua` `/modo_casa` `/audio_hibrido`  
`/dissuasao` `/gravar` `/viagem` `/lista` `/gastos`  
`/tela` `/processos` `/reiniciar` `/cmd` `/backup` `/help`

---

## Protocolos e segurança

- **190** — iCSee + visão + WhatsApp/Telegram, **sem TTS na casa**
- **demo** — demonstração falada
- **dissuasão** — volume, luzes, alerta vocal, sirene
- **sentinel_patrol** — ronda / encomenda / ausente
- **anti_sabotagem_energia** — alerta AC→bateria (boot)

---

## Pacote cognitivo (novas)

`diario_cognitivo` · `tutor_conversacao` · `cacador_ofertas` · `mestre_feynman` · `guardiao_postura` · `radar_dispositivos_wifi` · `escritorio_documentos` · `mestre_rpg` · `curador_nicho` · `engenheiro_noturno`

## Actions 24/7

`protocolo`, `sentinel_patrol`, `smart_home`, `daily_ops`, `telegram_commander`, `audio_channel`, `protocolo_dissuasao`, `anti_sabotagem_energia`, `gravador_caixa_preta`, `simulador_presenca`, `controle_media_casa`, `modo_foco`, `lista_compras`, `controle_gastos`, `lembretes_persistentes`, `remote_pc_admin`, `backup_nuvem`, …

Boot automático: Telegram · energia · lembretes · backup domingo 03:00.

---

## Instalação

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
# opcional local: pip install -r requirements.txt
python -m main
# air-gapped:
python -m main  # use action offline para bunker
```

Recomenda-se **ffmpeg** no PATH (voz Telegram e conversões).

---

## Modo 24/7 (Windows)

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\install_24h.ps1
```

Cria venv, `rodar_jarvis_24h.bat`, atalho de Inicialização, `powercfg` AC=0 e tarefa 04:00.

---

## Variáveis `.env`

```bash
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EMERGENCY_CONTACT_PHONE=5517...
EMERGENCY_CONTACT_NAME=
HOME_ADDRESS=Rua Exemplo, nº 00, nº 244, Jardim Europa, Cidade Exemplo - SP
ICSEE_APP_PATH=
ICSEE_RTSP_URL=
AUDIORELAY_PATH=
TUYA_DEVICE_ID=
TUYA_IP=
TUYA_LOCAL_KEY=
WOL_MAC=
```

---

## Licença

© 2026 Guilherme · **J.A.R.V.I.S. — MARK LXI (61)** · [CC BY-NC 4.0](LICENSE) — uso comercial não permitido.


## Offline / MCP
- `/offline` `/online` `/preparar_offline` `/mcp`
- Config: `config/mcp_servers.json`


---

## UPGRADE_4_FEATURES.md

<a id="upgrade-4-features-md"></a>

# Upgrade: MCP · Realtime · Episodic/Graph memory · GUI validate loop

Implemented as optional, non-breaking layers on top of the existing architecture.

## 1. MCP (Model Context Protocol)

| File | Change |
|------|--------|
| `core/mcp_client.py` | **NEW** — stdio MCP client, tool schema adapter, `call_tool` |
| `core/plugin_loader.py` | After local plugins, merges MCP tools as `PluginRecord`s |
| `config/mcp_servers.json.example` | **NEW** — example server list |

**Setup**
```bash
pip install mcp
cp config/mcp_servers.json.example config/mcp_servers.json
# edit servers (npx + official MCP packages, tokens in env)
```
Tools appear as `mcp_<server>__<tool_name>` and go through the normal plugin path.

## 2. OpenAI Realtime (native audio WebSocket)

| File | Change |
|------|--------|
| `providers/engine_openai_realtime.py` | **NEW** — Live-shaped engine over OpenAI Realtime API |
| `providers/registry.py` | Registers `engine_openai_realtime` under `engine` |

**Setup**
```bash
pip install websockets
```
Select **OpenAI Realtime** in the providers panel; set API key + model.
Gemini Live remains the default path. Viseme / barge-in / tools reuse the same `Msg` contract.

## 3. Episodic memory + knowledge graph

| File | Change |
|------|--------|
| `memory/memory_manager.py` | Episodes (`episodes.jsonl`), graph (`graph.json`), optional Chroma, `search_memory_rich` |
| `actions/memory_compactor.py` | Status shows episode/graph stats; `action=compact_episodes` |
| `main.py` | `recall_memory` uses `search_memory_rich` |

**API (Python)**
- `add_episode(text, role=..., entities=[...], summary=...)`
- `search_episodes(query)`
- `upsert_node` / `link` / `related`
- `search_memory_rich(query)` — facts + episodes + graph

**Optional**
```bash
pip install chromadb   # semantic episode search
```

Prompt budget is unchanged: only the core block is injected; episodes/graph are tool-on-demand.

## 4. GUI grounding — Observar → Agir → Validar

| File | Change |
|------|--------|
| `plugins/desktop_agent.py` | `_screen_fingerprint`, `_validate_action`, loop wires validate after every act |

After each action the agent:
1. Snapshots a cheap `phash` before the act
2. Executes
3. Validates pixel change + optional fast Gemini check
4. On `validate_fail` → treated as failure → existing `_replan` path

Works with the existing UIA / vision / Playwright stack; no new required deps.

## Optional packages (summary)

```bash
pip install mcp websockets chromadb
```

None of these are required for boot. Missing packages are logged and skipped.


---

## UPGRADE_QUALITY_LAYERS.md

<a id="upgrade-quality-layers-md"></a>

# Upgrade: Quality layers (reliability · memory · voice · security · extensibility · UX)

Non-breaking modules layered on the existing architecture. Missing optional
pieces are skipped; core boot does not require them.

## 1. Reliability

| File | Role |
|------|------|
| `core/contracts.py` | Risk tiers (`safe` / `review` / `destructive` / `autonomous`), TOOL schema helpers, outcome assertion helpers for tests |
| `core/retry.py` | Exponential backoff + per-tool circuit breaker |
| `core/sandbox.py` | Thread-local dry-run, allow-listed path policy |
| `tests/test_action_contracts.py` | Existing golden shape tests (unchanged) |
| `tests/test_quality_layers.py` | **NEW** — contracts, retry, sandbox, redaction, agent mode, memory hygiene |

Tools may declare `"risk": "destructive"` in their `TOOL` / `PLUGIN` dict.
Destructive heuristics also look at `action=delete|shutdown|…`.

## 2. Memory quality

| API | Purpose |
|-----|---------|
| `consolidate_episodes()` | Promote frequent episode topics → graph + long-term facts; TTL prune |
| `forget_old_episodes(ttl_days=30)` | Drop stale episode lines |
| `detect_contradictions()` | Same key, conflicting values |
| `memory_hygiene_report()` | Human-readable summary |

Exposed via `memory_compactor` actions: `consolidate`, `hygiene`, `forget_old`.

## 3. Voice & latency

| Change | Detail |
|--------|--------|
| `actions/audio_latency_tuner.py` | New `action=auto` — A/B probe of buffer sizes, applies best to `config/audio_latency.json` |
| `core/network_fallback.py` | `should_use_local()` / `internet_reachable()` for cloud → offline hand-off |

## 4. Security & privacy

| File | Role |
|------|------|
| `core/redaction.py` | Mask API keys, tokens, passwords (optional soft PII) before logs |
| `core/audit.py` | Append-only JSONL under `memory/audit/audit_YYYY-MM-DD.jsonl` |
| `core/agent_mode.py` | `air_gapped` flag blocks known cloud tools |

`main.py` redacts tool args in console output and audits high-stakes tools.

## 5. Extensibility

| Change | Detail |
|--------|--------|
| `core/contracts.py` | Shared formal TOOL validation (risk, requires_confirm) |
| `actions/hot_reload.py` | Failed reload restores last-good module; one broken file does not abort the batch |
| `config/mcp_servers.json.example` | Expanded examples: filesystem, github, memory, git, brave_search, sqlite |

## 6. UX — mode + validate feedback

| Piece | Detail |
|-------|--------|
| `core/agent_mode.py` | Modes: `listen` (no actuation), `assist` (default), `autonomous` |
| `actions/agent_mode_control.py` | Tool to set mode / air_gap / strict_paths / validate_feedback |
| `config/agent_mode.json` | Persistence (created on first change) |
| `core/action_feedback.py` | Toasts for `validate_fail` / `validate_ok` from desktop_agent |
| `main.py` | Gate: listen-only blocks actuation; sandbox dry-run short-circuits |

### Mode labels (PT)

- **somente escuta** — ouve e responde; não move mouse/arquivos
- **assistente** — padrão, com confirms
- **autônomo** — agentes multi-step mais livres (destrutivo ainda pede confirm)

## Quick start

```bash
# optional deps already listed in requirements where needed
python tests/test_quality_layers.py
python tests/test_action_contracts.py

# switch mode by voice/tool
# agent_mode_control action=set mode=listen
# memory_compactor action=consolidate
# audio_latency_tuner action=auto
```

## Integration notes

- Quality imports in `main.py` are wrapped in `try/except` so an older tree
  without these files still boots.
- Circuit breaker state is process-local (clears on restart).
- Audit log is best-effort and never raises into the tool path.

## 8. Default local model

Default Ollama model is now **`qwen2.5-coder:7b`** in:

- `core/llm_client.py` (`_DEFAULTS`)
- `core/offline_assistant.py` (`MODEL_NAME`)
- `config/api_keys.json` / `api_keys.json.example`

Pull once:

```bash
ollama pull qwen2.5-coder:7b
```

## 9. Biometrics (voice + face)

| Module | Role |
|--------|------|
| `core/voice_auth.py` | Enroll/verify WAV → spectral fingerprint, cosine score |
| `core/face_auth.py` | Enroll/verify image/camera → OpenCV hist (or face_recognition if installed) |
| `actions/biometrics.py` | Tool: `status / enroll / verify / clear` with `kind=voice\|face` |

Profiles: `memory/biometrics/voice_profile.json`, `face_profile.json` (fingerprints only).

```text
biometrics action=enroll kind=voice wav_path=/path/to/me.wav
biometrics action=verify kind=voice wav_path=/path/to/probe.wav
biometrics action=enroll kind=face camera=true
biometrics action=verify kind=face camera=true
```

Voice works with **stdlib + numpy** only. Face needs **opencv-python** (already in requirements; use 4.x — OpenCV 5 may drop Haar helpers).

## Dependency check

```bash
python scripts/check_deps.py
```


---
