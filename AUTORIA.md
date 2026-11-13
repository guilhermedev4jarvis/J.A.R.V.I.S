# Autoria e identidade

- **Nome do aplicativo e do assistente padrão:** J.A.R.V.I.S. — MARK LXI (61)
- **Autoria do projeto:** Guilherme
- **Licença:** Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)

A interface, o instalador, o dashboard e a landing page apresentam essa identidade.
Créditos e licenças de bibliotecas e ativos de terceiros permanecem preservados nos
respectivos locais do repositório.

## Inicialização e privacidade de voz

Na primeira execução, o **J.A.R.V.I.S.** pode ser configurado para iniciar no login do
usuário. Essa opção pode ser desligada em Controles; a escolha é persistida.

A ativação por voz (wake word) é **opcional**. Ao configurá-la, os modelos locais são
baixados uma vez. Em espera, o reconhecimento local aceita:

| Wake word |
|-----------|
| “Jarvis” |
| “J.A.R.V.I.S.” |
| “Mark LXI” |
| “Hey Jarvis” |

O áudio de espera **não** é enviado ao serviço de conversa em nuvem.

## Biometria do dono

O boot biométrico é **sequencial**: face → voz, com feedback TTS e overlay na UI.
Threshold padrão de parecença de voz: **0.75**.
