"""
action_feedback — turn tool outcomes into short Portuguese UI messages.

Shown as on-screen toasts after every automation request so the user sees
whether something actually worked, without relying only on speech.
"""
from __future__ import annotations

import re
from typing import Optional


def _status(result: str) -> str:
    m = re.search(r"status=(\w+)", result or "")
    return (m.group(1) if m else "").lower()


def _fact(result: str, key: str) -> Optional[str]:
    # key=value or key="quoted value"
    m = re.search(rf'{re.escape(key)}=("([^"]*)"|(\S+))', result or "")
    if not m:
        return None
    return m.group(2) if m.group(2) is not None else m.group(3)


def _action_name(result: str, tool_name: str) -> str:
    return _fact(result, "action") or tool_name


# Human labels for tools (Portuguese)
_TOOL_LABELS = {
    "open_app": "abrir aplicativo",
    "browser_control": "navegador",
    "clipboard_smart": "área de transferência",
    "window_manager": "janelas",
    "powershell_cmd": "comando do sistema",
    "system_health": "saúde do sistema",
    "file_organize": "organizar arquivos",
    "file_controller": "arquivos",
    "focus_timer": "timer de foco",
    "code_review_local": "revisão de código",
    "email_triage": "e-mail",
    "meeting_brief": "reunião",
    "web_search": "busca na web",
    "youtube_video": "YouTube",
    "weather_report": "clima",
    "computer_control": "controle do computador",
    "computer_settings": "configurações",
    "send_message": "mensagem",
    "desktop": "área de trabalho",
    "screen_processor": "tela",
}


def format_feedback(tool_name: str, result: str, args: dict | None = None) -> tuple[str, str]:
    """
    Returns (level, message_pt) where level is success|error|info|warn.
    """
    args = args or {}
    st = _status(result)
    label = _TOOL_LABELS.get(tool_name, tool_name.replace("_", " "))

    # desktop_agent validate loop feedback
    if "validate_fail" in (result or "").lower() or "status=failed" in (result or "") and "validate" in (result or "").lower():
        return "error", f"Validação falhou em {label}: a tela não mudou como esperado"
    if "validate_ok" in (result or "").lower() or "validated=true" in (result or "").lower():
        return "success", f"Ação validada na tela ({label})"

    # ── open_app ──────────────────────────────────────────────────────────
    if tool_name == "open_app":
        app = args.get("app_name") or _fact(result, "app") or "aplicativo"
        if st == "done":
            return "success", f"Aplicativo aberto: {app}"
        if st == "started":
            return "info", f"Abrindo {app}…"
        if st == "unverified":
            return "warn", f"Pedido para abrir {app}, mas não confirmei se abriu"
        return "error", f"Não foi possível abrir {app}"

    # ── browser ───────────────────────────────────────────────────────────
    if tool_name == "browser_control":
        url = args.get("url") or args.get("query") or _fact(result, "url") or "página"
        action = (args.get("action") or _fact(result, "action") or "").lower()
        if "youtube" in str(url).lower() or "youtube" in str(args).lower():
            target = "YouTube (youtube.com)"
        else:
            target = str(url)[:80]
        if st in ("done", "started"):
            if action in ("open", "navigate", "goto", "search", ""):
                return "success", f"Aba aberta no navegador padrão: {target}"
            return "success", f"Navegador: {action or 'ação'} — {target}"
        if st == "unverified":
            return "warn", f"Tentei abrir no navegador: {target} (sem confirmação)"
        return "error", f"Não foi possível abrir no navegador: {target}"

    # ── youtube ───────────────────────────────────────────────────────────
    if tool_name == "youtube_video":
        q = args.get("query") or args.get("url") or "YouTube"
        if st in ("done", "started"):
            return "success", f"YouTube: {q}"
        return "error", f"Não foi possível abrir o YouTube ({q})"

    # ── window manager ────────────────────────────────────────────────────
    if tool_name == "window_manager":
        title = args.get("title") or args.get("name") or _fact(result, "title") or "janela"
        act = (args.get("action") or _fact(result, "action") or "").lower()
        if st == "done":
            if act == "list":
                return "success", "Lista de janelas atualizada"
            if act in ("focus", "activate"):
                return "success", f"Janela em foco: {title}"
            if act in ("minimise", "minimize"):
                return "success", f"Janela minimizada: {title}"
            if act == "close":
                return "success", f"Pedido para fechar: {title}"
            return "success", f"Janela: {act} — {title}"
        return "error", f"Não foi possível controlar a janela: {title}"

    # ── clipboard ─────────────────────────────────────────────────────────
    if tool_name == "clipboard_smart":
        act = (args.get("action") or _fact(result, "action") or "read").lower()
        if st == "done":
            if act in ("read", "show", "get"):
                return "success", "Área de transferência lida"
            if act in ("summarise", "summarize"):
                return "success", "Resumo da área de transferência pronto"
            if act == "write":
                return "success", "Texto copiado para a área de transferência"
            return "success", f"Área de transferência: {act}"
        return "error", "Falha na área de transferência"

    # ── shell ─────────────────────────────────────────────────────────────
    if tool_name == "powershell_cmd":
        cmd = (args.get("command") or args.get("cmd") or "")[:60]
        if st == "done":
            return "success", f"Comando executado: {cmd or 'ok'}"
        if st == "ask":
            return "warn", "Comando precisa de confirmação (force=true)"
        return "error", f"Comando falhou: {cmd or _fact(result, 'reason') or 'erro'}"

    # ── files ─────────────────────────────────────────────────────────────
    if tool_name in ("file_organize", "file_controller", "file_processor"):
        if st == "done":
            return "success", f"{label.capitalize()}: concluído"
        if st == "ask":
            return "warn", "Confirme a ação de arquivos para continuar"
        return "error", f"Falha em {label}: {_fact(result, 'reason') or 'erro'}"

    # ── system ────────────────────────────────────────────────────────────
    if tool_name == "system_health":
        if st == "done":
            cpu = _fact(result, "cpu_percent") or "?"
            mem = _fact(result, "memory_percent") or "?"
            return "success", f"Sistema: CPU {cpu}% · RAM {mem}%"
        return "error", "Não foi possível ler a saúde do sistema"

    if tool_name == "focus_timer":
        act = (args.get("action") or _fact(result, "action") or "").lower()
        if st == "done":
            if act == "start":
                return "success", f"Timer de foco iniciado ({_fact(result, 'minutes') or '?'} min)"
            if act == "stop":
                return "success", "Timer de foco parado"
            if act == "status":
                if _fact(result, "active") == "true":
                    return "info", f"Foco ativo · restam {_fact(result, 'remaining_minutes') or '?'} min"
                return "info", "Nenhum timer de foco ativo"
            return "success", "Timer de foco atualizado"
        return "error", "Falha no timer de foco"

    # ── generic ───────────────────────────────────────────────────────────
    reason = _fact(result, "reason") or ""
    if st == "done":
        return "success", f"{label.capitalize()}: concluído"
    if st == "started":
        return "info", f"{label.capitalize()}: em andamento…"
    if st == "unverified":
        return "warn", f"{label.capitalize()}: pedido enviado, sem confirmação"
    if st == "ask":
        return "warn", f"{label.capitalize()}: precisa da sua confirmação"
    if st == "failed":
        return "error", f"Não foi possível ({label})" + (f": {reason}" if reason else "")
    # Fallback for free-form results
    if result and len(result) < 120 and "status=" not in result:
        return "info", result
    return "info", f"{label.capitalize()}: processado"
