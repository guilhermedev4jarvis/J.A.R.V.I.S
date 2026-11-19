"""Human-visible ChatGPT/Grok handoff and local improvement-idea notes."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
IDEAS_FILE = APP_ROOT / "updates" / "improvement_ideas.md"


def _assistant_name() -> str:
    try:
        from memory.config_manager import get_assistant_name
        return get_assistant_name()
    except Exception:
        return "J.A.R.V.I.S."


def _suggestion_prompt(focus: str = "") -> str:
    focus_line = f"Focus area: {focus.strip()}\n" if focus.strip() else ""
    assistant_name = _assistant_name()
    return (
        f"I use {assistant_name}, a Python desktop voice assistant. It uses Gemini Live for "
        "online voice conversations and Ollama llama3.1:8b with local Whisper and "
        "Kokoro pf_dora when offline. It has browser control, desktop tools, local "
        "memory, plugins, and a Portuguese-Brazilian interface.\n\n"
        f"{focus_line}Suggest up to five practical improvements for {assistant_name}. Rank them "
        "by user benefit, explain effort and risks briefly, and distinguish ideas "
        "that require an API or internet from ideas that can run locally. Do not "
        "claim to have inspected its source code. Do not ask for secrets or personal data."
    )


def _save_ideas(provider: str, text: str) -> str:
    IDEAS_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    with IDEAS_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\n\n## {stamp} — {provider}\n\n{text.strip()}\n")
    return str(IDEAS_FILE)


def ai_collaboration(parameters: dict, player=None, speak=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "chat").strip().lower()
    provider = str(p.get("provider") or "chatgpt").strip().lower()
    browser = str(p.get("browser") or "chrome").strip().lower()
    prompt = str(p.get("prompt") or "").strip()

    if action == "save_ideas":
        if not prompt:
            return "Cole no campo de texto as sugestões que trouxe do ChatGPT ou Grok."
        path = _save_ideas(provider, prompt)
        return f"Sugestões salvas localmente em {path}. Nenhum código foi alterado."

    if action == "list_ideas":
        if not IDEAS_FILE.exists():
            return "Ainda não há sugestões salvas."
        return IDEAS_FILE.read_text(encoding="utf-8")[-8_000:]

    if action not in ("chat", "suggest_improvements"):
        return "Ação disponível: chat, suggest_improvements, save_ideas ou list_ideas."

    if action == "suggest_improvements":
        prompt = _suggestion_prompt(prompt)
    elif not prompt:
        return "Diga o que devo perguntar ao ChatGPT ou Grok."

    providers = ["chatgpt", "grok"] if provider == "both" else [provider]
    if any(name not in ("chatgpt", "grok") for name in providers):
        return "Escolha ChatGPT, Grok ou ambos."

    try:
        from actions.web_media.browser_control import _registry
        session = _registry.get(browser)
        results = [
            session.run(session.open_ai_chat(name, prompt), timeout=60)
            for name in providers
        ]
    except Exception as exc:
        return f"Não consegui abrir a conversa no navegador: {exc}"

    if player:
        for name in providers:
            try:
                player.write_log(f"IA externa aberta: {name.capitalize()} ({browser}).")
            except Exception:
                pass
    return " ".join(results)


TOOL = {
    "name": "ai_collaboration",
    "description": (
        "Conversa com ChatGPT ou Grok pela interface visível do navegador, sem API. "
        "Use somente quando a pessoa pedir explicitamente. Envia a pergunta e deixa "
        "a resposta na página para a pessoa ler/copiar; não lê nem extrai respostas "
        "automaticamente. Também salva ou lista sugestões que a pessoa colar no assistente. "
        "Não envie memória, arquivos ou dados privados sem pedido explícito."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "chat | suggest_improvements | save_ideas | list_ideas",
            },
            "provider": {
                "type": "STRING",
                "description": "chatgpt | grok | both (both opens the same question in each)",
            },
            "prompt": {
                "type": "STRING",
                "description": "Pergunta, foco para sugestões ou texto de ideias colado pelo usuário",
            },
            "browser": {
                "type": "STRING",
                "description": "chrome | edge | firefox | brave | vivaldi | opera (default chrome)",
            },
        },
        "required": ["action"],
    },
    "handler": ai_collaboration,
}
