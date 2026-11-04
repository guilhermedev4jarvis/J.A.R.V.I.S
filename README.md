# JARVIS Project - MARK LVI

Este repositório contém o código-fonte e a arquitetura do **JARVIS (MARK LVI)**, um ecossistema avançado de assistente virtual automatizado e agente autônomo baseado em inteligência artificial. O projeto está estruturado em módulos independentes e extensíveis que abrangem desde automação de desktop e processamento de linguagem natural (STT/TTS) até monitoramento proativo de sistema e integração com modelos de linguagem (LLMs).

---

## 🚀 Estrutura do Projeto

O projeto está organizado da seguinte forma:

### 1. `actions/` (Ações de Automação e Assistência)
Esta pasta contém os módulos responsáveis por executar tarefas específicas do sistema e do usuário:
*   **`ai_collaboration.py`**: Gerencia fluxos de trabalho colaborativos assistidos por IA.
*   **`background_monitor.py` & `system_monitor.py`**: Monitoram continuamente processos, threads e eventos em segundo plano.
*   **`bank_statement.py`**: Analisa e processa extratos bancários automaticamente.
*   **`battery.py`**: Monitora o status da bateria e otimiza o consumo energético.
*   **`browser_control.py`**: Controle automatizado de navegadores web (abrir abas, navegação).
*   **`clipboard.py` & `clipboard_smart.py`**: Monitoramento inteligente e manipulação da área de transferência com análise de contexto.
*   **`code_helper.py` & `code_review_local.py`**: Assistente de desenvolvimento integrado que realiza revisões de código locais em tempo real.
*   **`computer_control.py` & `computer_settings.py`**: Controle de hardware, periféricos e alteração de configurações do sistema operacional.
*   **`deep_research.py`**: Módulo de pesquisa aprofundada na web com síntese de informações.
*   **`desktop.py`**: Gerenciamento de janelas, ícones e automação da interface gráfica (GUI).
*   **`dev_agent.py`**: Agente autônomo focado em desenvolvimento de software (criação e correção de arquivos).
*   **`email_triage.py`**: Triagem e categorização automática de e-mails recebidos.
*   **`file_controller.py`, `file_organize.py` & `file_processor.py`**: Módulos completos para criação, leitura, processamento e organização automática de arquivos e diretórios.
*   **`flight_finder.py`**: Busca e monitoramento de passagens aéreas e itinerários.
*   **`focus_timer.py` & `timer.py`**: Gerenciamento de tempo, alarmes e cronômetros de foco (Pomodoro).
*   **`game_helper.py` & `game_updater.py`**: Otimização de ambiente para jogos e automação de atualizações.
*   **`media_control.py`**: Controle global de reprodução de mídia (play, pause, volume, faixas).
*   **`meeting_brief.py`**: Cria resumos executivos e pautas automáticas para reuniões.
*   **`network_status.py`**: Monitora a integridade, velocidade e latência da conexão de rede.
*   **`open_app.py`**: Inicialização rápida de aplicações instaladas no sistema.
*   **`powershell_cmd.py`**: Execução segura de comandos PowerShell e scripts administrativos.
*   **`proactive.py`**: Motor de tomada de decisões proativas com base no comportamento do usuário.
*   **`process_manager.py`**: Listagem, encerramento e gerenciamento de prioridade de processos do SO.
*   **`quick_note.py`**: Captura rápida de notas e ideias sem interrupção de fluxo.
*   **`reminder.py`**: Sistema de lembretes persistentes com agendamento cronometrado.
*   **`screen_processor.py` & `screenshot_ocr.py`**: Captura de tela, processamento de imagem e reconhecimento óptico de caracteres (OCR).
*   **`send_message.py`**: Integração para envio de mensagens em plataformas externas.
*   **`system_health.py`**: Diagnóstico de integridade do sistema operacional e detecção de falhas.
*   **`unit_convert.py`**: Conversor universal de unidades e moedas.
*   **`video_player.py` & `youtube_video.py`**: Manipulação e automação de players de vídeo locais e streaming do YouTube.
*   **`weather_report.py` & `web_search.py`**: Consulta meteorológica e motor de busca web avançado.

### 2. `core/` (O Núcleo do Sistema)
O motor central que orquestra a inteligência, a interface lógica e os pipelines do JARVIS:
*   **`action_feedback.py` & `action_loader.py`**: Sistema dinâmico de carregamento e validação de ações, fornecendo feedback de execução.
*   **`appidentity.py`**: Identidade, assinatura e segurança dos módulos da aplicação.
*   **`audio_devices.py`**: Gerenciamento de drivers, microfones e canais de saída de áudio.
*   **`avatar.py` & `avatar_mesh.py`**: Gerenciamento do avatar tridimensional visual do JARVIS.
*   **`face_model.obj`**: Modelo 3D de malha poligonal utilizado para a renderização da interface visual da IA.
*   **`confirm.py`**: Mecanismo de segurança de dupla confirmação antes de executar ações críticas.
*   **`echo.py` & `viseme.py`**: Sincronização labial (visemas) e respostas de áudio integradas ao avatar.
*   **`gemini.py` & `llm_client.py`**: Cliente de integração de alto nível com a API do Google Gemini e infraestrutura abstrata de LLM.
*   **`hotkey.py`**: Gerenciador global de atalhos de teclado (Keybinds).
*   **`installer.py`**: Scripts de instalação automática de dependências e binários do sistema.
*   **`lazyimport.py`**: Otimizador de tempo de inicialização por meio de carregamento preguiçoso de bibliotecas pesadas.
*   **`offline_assistant.py`**: Pipeline alternativo de regras de execução para quando o sistema estiver sem conexão com a internet.
*   **`outcome.py`**: Estruturação dos resultados e outputs gerados pelas execuções do JARVIS.
*   **`platform_support.py`**: Camada de abstração que permite a portabilidade entre diferentes sistemas operacionais.
*   **`plugin_loader.py`**: Carregador assíncrono para a pasta `plugins/`.
*   **`prompt.txt`**: System prompt base que dita a personalidade, regras e comportamento da IA.
*   **`stt.py` & `tts.py`**: Pipelines locais/em nuvem de Speech-to-Text (reconhecimento de voz) e Text-to-Speech (síntese de voz).
*   **`undo.py`**: Mecanismo de reversão e rollback de ações indesejadas realizadas pelo assistente.
*   **`wake_word.py`**: Motor de escuta contínua de ultrabaixo consumo para ativação por voz ("Wake Word").

### 3. `dashboard/` & `config/` (Interface e Configurações)
*   **`server.py` & `static/ (app.html, login.html, crypto-js.min.js)`**: Servidor web local integrado que serve o painel de controle (Dashboard) gráfico do JARVIS, protegido por autenticação criptografada.
*   **`api_keys.json`**: Arquivo de armazenamento seguro das credenciais de API (Gemini, ElevenLabs, etc.).
*   **`autostart_state.json`**: Estado de configuração de inicialização junto com o Sistema Operacional.
*   **`jarvis.ico` / `jarvis_icon_*.png`**: Ativos de imagem e ícones em resoluções variadas (16px a 512px) para o tray e janelas do sistema.

### 4. `memory/` (Memória e Contexto)
*   **`config_manager.py` & `memory_manager.py`**: Gerenciamento do armazenamento persistente de curto e longo prazo.
*   **`long_term.json`**: Base de conhecimento em JSON que guarda preferências, fatos aprendidos e dados históricos do usuário.

### 5. `plugins/` (Extensões Modulares)
Módulos independentes adicionais que estendem as capacidades nativas do assistente:
*   **`baixar_arquivo.py`**: Utilitário para download de mídias e arquivos.
*   **`clima.py` & `cotacao_dolar.py`**: Atalhos rápidos para cotações financeiras e dados climáticos.
*   **`desktop_agent.py`**: Plugin para coordenação de tarefas de agentes de interface.
*   **`modo_treinador.py` & `treinador_base/`**: Sistema embarcado para análise de metodologias esportivas (com arquivos anexos sobre dietas, treinos e táticas para futebol sub-13 baseados em modelos oficiais como o da FIGC).
*   **`noticias_brasil.py`**: Raspador de canais locais de notícias brasileiras.
*   **`resumo_link.py`**: Extrai e sintetiza o conteúdo textual de links web fornecidos.
*   **`system_resources_monitor.py`**: Monitor gráfico de uso de CPU, GPU e RAM.
*   **`whatsapp_web.py`**: Automação para envio e leitura de notificações no WhatsApp Web.
*   **`pending/`**: Pasta contendo integrações em desenvolvimento, como o monitor de hardware avançado (`hwmonitor_integration.py`).

### 6. `providers/` (Camada de Hardware e Modelos de Entrada)
Mapeamento de baixo nível para APIs e serviços específicos:
*   **`audio.py`**: Pipeline de buffer e streaming de áudio cru.
*   **`base.py` & `registry.py`**: Classes abstratas e de registro para novos providers.
*   **`engine_pipeline.py`**: Orquestrador do fluxo contínuo Entrada de Áudio -> STT -> LLM -> TTS -> Saída de Áudio.
*   **`llm_openai.py`**: Provider alternativo para modelos compatíveis com o ecossistema OpenAI.
*   **`schema.py`**: Definições de estruturas de dados estritas.
*   **`stt_whisper.py`**: Integração com o Whisper para transcrição precisa de áudio.
*   **`tts_elevenlabs.py` & `tts_piper.py`**: Drivers para síntese de voz realista (ElevenLabs em nuvem e Piper para execução 100% offline e local).

### 7. Arquivos da Raiz
*   **`main.py`**: O ponto de entrada principal do ecossistema JARVIS, inicializando todos os providers, o núcleo, carregando memórias e abrindo o servidor do painel.
*   **`ui.py`**: Gerencia a interface de usuário local da aplicação (janela nativa ou ícone de bandeja do sistema).
*   **`prepare_offline.py`**: Utilitário para baixar localmente todos os pesos e modelos necessários para o funcionamento offline.
*   **`requirements.txt` & `requirements-local.txt`**: Listas de dependências de pacotes pip para ambientes online e offline, respectivamente.
*   **`setup.py`**: Script de empacotamento do projeto.

---

## 🛠️ Requisitos de Sistema e Instalação

1.  **Instalação Online:**
    ```bash
    pip install -r requirements.txt
    python main.py
    ```
2.  **Preparação para Uso Offline:**
    ```bash
    python prepare_offline.py
    pip install -r requirements-local.txt
    ```

---

## 🛡️ Licença e Autoria
*   **Autoria:** Consulte o arquivo `AUTORIA.md` para ver a lista de contribuidores.
*   **Licença:** Este projeto está sob a licença descrita em `LICENSE`.