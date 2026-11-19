"""
Action: whatsapp_web — abrir WhatsApp Web, pesquisar contato e enviar mensagem.

Dependência Gemini:
    pip install --upgrade google-genai

Windows PowerShell (configure uma vez; reinicie o JARVIS depois):
    setx GEMINI_API_KEY "SUA_CHAVE_GEMINI"

Opcional:
    setx GEMINI_MODEL "gemini-3.8-flash"

O fluxo send prepara o texto e aguarda uma chamada confirm_send após a confirmação
explícita do usuário. Sem aprovação visual do Gemini ou sem confirmação, não envia.

Qualquer intenção envolvendo "WhatsApp" deve chamar esta tool (não open_app
isolado nem send_message genérico).

Modos:
  open            → abre https://web.whatsapp.com e pergunta o contato
  search_contact  → abre/foca, pesquisa o contato e abre a conversa
  send            → fluxo completo (contact + message); pergunta o que faltar

Método principal: Playwright (seletores da caixa de pesquisa e do campo de
mensagem). Fallback: pyautogui + pyperclip (atalho Ctrl/Cmd+Alt+/ e clipboard).
"""

from __future__ import annotations

import importlib.util
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any, Optional

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # a ação continua importável até a SDK ser instalada
    genai = None
    genai_types = None

from core.outcome import ask, done, failed, unverified
from core.lazyimport import LazyModule, installed

_PYAUTOGUI = installed("pyautogui")
_PYPERCLIP = installed("pyperclip")
_HAS_PLAYWRIGHT = importlib.util.find_spec("playwright") is not None

_WA_URL = "https://web.whatsapp.com"
_WA_WEB_URL = "https://web.whatsapp.com"  # sempre Web

# Configure GEMINI_API_KEY no ambiente do Windows; nunca grave a chave no código.
_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
_PENDING_SENDS: dict[str, dict[str, Any]] = {}
_PENDING_TTL_SECONDS = 600  # confirmações expiram após 10 minutos


class _GeminiVerificationError(RuntimeError):
    """A análise visual não pôde ser concluída com segurança."""

_SEARCH_SELECTORS = [
    'div[contenteditable="true"][data-tab="3"]',
    'div[contenteditable="true"][title*="Pesquisar"]',
    'div[contenteditable="true"][title*="Search"]',
    '[aria-label*="Pesquisar"]',
    '[aria-label*="Search"]',
    'div[contenteditable="true"][data-tab="3"][role="textbox"]',
]
_MESSAGE_SELECTORS = [
    'div[contenteditable="true"][data-tab="10"]',
    'footer div[contenteditable="true"]',
    'div[contenteditable="true"][data-tab="10"][role="textbox"]',
    'div[contenteditable="true"][title*="Mensagem"]',
    'div[contenteditable="true"][title*="Type a message"]',
]


def _configure_pyautogui(module) -> None:
    module.FAILSAFE = True
    module.PAUSE = 0.06


pyautogui = LazyModule("pyautogui", _configure_pyautogui)
pyperclip = LazyModule("pyperclip")


def _log(player, msg: str) -> None:
    if player:
        try:
            player.write_log(f"JARVIS: {msg}")
        except Exception:
            pass


def _open_whatsapp_url() -> bool:
    """Abre sempre https://web.whatsapp.com (nunca whatsapp.com)."""
    import webbrowser
    try:
        webbrowser.open("https://web.whatsapp.com")
        return True
    except Exception:
        return False


def _wait_whatsapp_web_ready_playwright(page, timeout_s: float = 45.0) -> str:
    """Espera interface do WhatsApp Web: caixa de pesquisa (logado) ou canvas/QR (não logado).
    Retorna "authenticated" | "qr" | "timeout".
    """
    deadline = time.time() + timeout_s
    qr_selectors = [
        'canvas[aria-label*="Scan"]',
        'canvas[aria-label*="QR"]',
        'div[data-ref]',
        'div[data-testid="qrcode"]',
        'canvas',
    ]
    while time.time() < deadline:
        for sel in _SEARCH_SELECTORS:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=400):
                    return "authenticated"
            except Exception:
                continue
        for sel in qr_selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=300):
                    # Ainda no QR — continua esperando sessão
                    break
            except Exception:
                continue
        time.sleep(0.7)
    # Última checagem de pesquisa
    for sel in _SEARCH_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=500):
                return "authenticated"
        except Exception:
            continue
    return "timeout"


def _wait_gui_settle(seconds: float = 6.0, player=None) -> None:
    """Aguarda carregamento inicial do WhatsApp Web no navegador padrão (GUI path)."""
    _log(player, f"Aguardando interface do WhatsApp Web (~{seconds:.0f}s)…")
    time.sleep(max(3.0, float(seconds)))


def _paste(text: str) -> None:
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI não instalado. Rode: pip install pyautogui pyperclip")
    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.12)
        if sys.platform == "darwin":
            pyautogui.hotkey("command", "v")
        else:
            pyautogui.hotkey("ctrl", "v")
    else:
        pyautogui.write(text, interval=0.03)
    time.sleep(0.15)


def _clear_field() -> None:
    if sys.platform == "darwin":
        pyautogui.hotkey("command", "a")
    else:
        pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("backspace")
    time.sleep(0.12)


def _focus_search_gui(player=None) -> None:
    if sys.platform == "darwin":
        pyautogui.hotkey("command", "alt", "/")
    else:
        pyautogui.hotkey("ctrl", "alt", "/")
    time.sleep(0.7)
    try:
        w, h = pyautogui.size()
        points = [
            (int(w * 0.14), int(h * 0.10)),
            (int(w * 0.12), int(h * 0.09)),
            (int(w * 0.18), int(h * 0.11)),
        ]
        for x, y in points:
            pyautogui.moveTo(x, y, duration=0.2)
            time.sleep(0.12)
            pyautogui.click()
            time.sleep(0.3)
        if sys.platform == "darwin":
            pyautogui.hotkey("command", "alt", "/")
        else:
            pyautogui.hotkey("ctrl", "alt", "/")
        time.sleep(0.45)
    except Exception:
        pass


def _search_and_open_contact_gui(contact: str, player=None) -> None:
    _focus_search_gui(player)
    _clear_field()
    _paste(contact)
    time.sleep(1.2)
    pyautogui.press("enter")
    time.sleep(1.0)
    try:
        _focus_search_gui(player)
        _clear_field()
        _paste(contact)
        time.sleep(1.1)
        pyautogui.press("enter")
        time.sleep(0.9)
    except Exception:
        pass


def _gemini_analyze_screenshot(
    contact: str,
    message: str,
    screenshot_path: str | Path = "screenshot.png",
    *,
    stage: str,
) -> dict[str, Any]:
    """Envia screenshot.png ao Gemini e confere contato, texto e etapa do envio."""
    if genai is None or genai_types is None:
        raise _GeminiVerificationError(
            "SDK Google GenAI ausente. Instale com: pip install --upgrade google-genai"
        )
    api_key = _GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise _GeminiVerificationError(
            "GEMINI_API_KEY não configurada. Defina a variável de ambiente antes de iniciar o JARVIS."
        )

    image_path = Path(screenshot_path)
    if not image_path.is_file():
        raise _GeminiVerificationError(f"Captura não encontrada: {image_path}")
    try:
        image_bytes = image_path.read_bytes()
    except OSError as exc:
        raise _GeminiVerificationError(f"Não foi possível ler {image_path}: {exc}") from exc
    if not image_bytes:
        raise _GeminiVerificationError("A captura screenshot.png está vazia.")

    if stage == "before_send":
        stage_rules = (
            "A conversa deve estar aberta para o contato esperado e o texto completo "
            "deve estar visível na caixa de composição, ainda NÃO enviado. O botão de "
            "envio visível não significa que a mensagem foi enviada."
        )
    elif stage == "after_send":
        stage_rules = (
            "A mensagem deve aparecer como uma mensagem enviada pelo usuário na conversa. "
            "Um balão de mensagem de saída visível é evidência; não afirme entrega ou leitura "
            "sem indicador visual inequívoco."
        )
    else:
        raise ValueError("stage precisa ser before_send ou after_send")

    prompt = f"""Você é um verificador visual conservador do WhatsApp Web.
Leia somente o que estiver visível na imagem. Não adivinhe texto cortado, contato oculto
ou estado de envio. Uma dúvida deve resultar em false.

Contato esperado: {contact!r}
Mensagem esperada (comparação exata, incluindo pontuação): {message!r}
Etapa: {stage}
Critério: {stage_rules}

Responda somente JSON válido com estas chaves:
{{
  "contact_matches": true,
  "message_matches": true,
  "send_state_matches": true,
  "visible_contact": "texto visível ou não identificado",
  "visible_message": "texto visível ou não identificado",
  "send_state": "draft_ready | sent | delivered | read | uncertain",
  "evidence": "breve evidência observável",
  "problems": ["problemas encontrados"]
}}
Para before_send, send_state_matches só pode ser true se o texto estiver no compositor,
pronto para envio, e não como mensagem já enviada. Para after_send, só pode ser true
se a mensagem esperada estiver visível como mensagem de saída. Não invente confirmação.
""".strip()

    client = None
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=[
                prompt,
                genai_types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/png" if image_path.suffix.lower() == ".png" else "image/jpeg",
                ),
            ],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
            ),
        )
        raw = response.text or ""
        result = json.loads(raw)
    except Exception as exc:
        raise _GeminiVerificationError(f"Falha na análise do Gemini: {exc}") from exc
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    if not isinstance(result, dict):
        raise _GeminiVerificationError("Gemini retornou uma resposta JSON inesperada.")
    result["approved"] = all(
        result.get(key) is True
        for key in ("contact_matches", "message_matches", "send_state_matches")
    )
    return result


def _print_gemini_result(result: dict[str, Any], player=None) -> None:
    summary = (
        "Gemini: contato={contact_matches}, mensagem={message_matches}, "
        "estado={send_state_matches}, observado={send_state}. Evidência: {evidence}"
    ).format(
        contact_matches=result.get("contact_matches"),
        message_matches=result.get("message_matches"),
        send_state_matches=result.get("send_state_matches"),
        send_state=result.get("send_state", "uncertain"),
        evidence=result.get("evidence", "sem evidência"),
    )
    _log(player, summary)
    for problem in result.get("problems", []) or []:
        _log(player, f"Gemini alerta: {problem}")


def _close_pending_state(state: dict[str, Any]) -> None:
    """Libera navegador/Playwright quando uma confirmação expira ou termina."""
    for key in ("context", "browser"):
        obj = state.get(key)
        if obj is not None:
            try:
                obj.close()
            except Exception:
                pass
    manager = state.get("playwright")
    if manager is not None:
        try:
            manager.stop()
        except Exception:
            pass


def _expire_pending_sends() -> None:
    now = time.monotonic()
    for token, state in list(_PENDING_SENDS.items()):
        if now - state.get("created_at", now) > _PENDING_TTL_SECONDS:
            _PENDING_SENDS.pop(token, None)
            _close_pending_state(state)


def _store_pending_send(contact: str, message: str, state: dict[str, Any], player=None) -> str:
    _expire_pending_sends()
    token = secrets.token_urlsafe(18)
    state.update({
        "contact": contact,
        "message": message,
        "created_at": time.monotonic(),
    })
    _PENDING_SENDS[token] = state
    _log(player, "Gemini aprovou o contato e o texto. Aguardando confirmação explícita do usuário.")
    return ask(
        "whatsapp_web",
        "O Gemini conferiu o contato e a mensagem. Deseja enviar agora? Responda CONFIRMAR para liberar o envio.",
        contact=contact,
        status="awaiting_confirmation",
        confirmation_token=token,
        visual_check="approved",
        message_preview=message[:160],
    )


def _prepare_playwright_send(contact: str, message: str, player=None, timeout_s: float = 45.0) -> str:
    """Abre a conversa e preenche o compositor, mas NÃO envia a mensagem."""
    from playwright.sync_api import sync_playwright

    manager = sync_playwright().start()
    browser = None
    context = None
    try:
        for channel in ("chrome", "msedge", "chromium", None):
            try:
                kwargs: dict[str, Any] = {"headless": False}
                if channel:
                    kwargs["channel"] = channel
                browser = manager.chromium.launch(**kwargs)
                break
            except Exception:
                continue
        if browser is None:
            raise RuntimeError("não foi possível iniciar Chromium/Chrome/Edge via Playwright")

        context = browser.new_context()
        page = context.new_page()
        page.goto(_WA_WEB_URL, wait_until="domcontentloaded", timeout=int(timeout_s * 1000))
        ready = _wait_whatsapp_web_ready_playwright(page, timeout_s=min(40.0, timeout_s))
        if ready != "authenticated":
            raise RuntimeError("WhatsApp Web não autenticado ou não ficou pronto; faça login e tente novamente")

        search = None
        deadline = time.time() + min(25.0, timeout_s)
        while time.time() < deadline and search is None:
            for selector in _SEARCH_SELECTORS:
                try:
                    locator = page.locator(selector).first
                    if locator.count() > 0 and locator.is_visible(timeout=500):
                        search = locator
                        break
                except Exception:
                    continue
            if search is None:
                time.sleep(0.5)
        if search is None:
            raise RuntimeError("caixa de pesquisa do WhatsApp Web não apareceu")

        search.click()
        search.fill(contact)
        time.sleep(1.2)
        page.screenshot(path="screenshot.png")
        page.keyboard.press("Enter")
        time.sleep(1.2)

        message_box = None
        deadline = time.time() + 12.0
        while time.time() < deadline and message_box is None:
            for selector in _MESSAGE_SELECTORS:
                try:
                    locator = page.locator(selector).first
                    if locator.count() > 0 and locator.is_visible(timeout=400):
                        message_box = locator
                        break
                except Exception:
                    continue
            if message_box is None:
                time.sleep(0.4)
        if message_box is None:
            raise RuntimeError(f"campo de mensagem não abriu para {contact!r}")

        message_box.click()
        message_box.fill(message)
        time.sleep(0.3)
        page.screenshot(path="screenshot.png")
        result = _gemini_analyze_screenshot(contact, message, "screenshot.png", stage="before_send")
        _print_gemini_result(result, player)
        if not result.get("approved"):
            raise _GeminiVerificationError(
                "Gemini não confirmou todos os itens antes do envio. Nada foi enviado. "
                f"Divergências: {result.get('problems', [])}"
            )

        # Mantém a página aberta enquanto aguarda a resposta do usuário.
        return _store_pending_send(contact, message, {
            "method": "playwright",
            "playwright": manager,
            "browser": browser,
            "context": context,
            "page": page,
        }, player)
    except Exception:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        try:
            manager.stop()
        except Exception:
            pass
        raise


def _prepare_gui_send(contact: str, message: str, player=None) -> str:
    """Prepara a mensagem com PyAutoGUI, captura a tela e aguarda confirmação."""
    if not _PYAUTOGUI:
        return failed(
            "whatsapp_web",
            "Playwright indisponível e PyAutoGUI não instalado. Instale playwright ou pyautogui+pyperclip.",
            contact=contact,
        )
    if not _open_whatsapp_url():
        return failed("whatsapp_web", "não foi possível abrir https://web.whatsapp.com", contact=contact)
    _wait_gui_settle(6.0, player)
    try:
        _search_and_open_contact_gui(contact, player)
        _paste(message)  # cola no campo, mas NÃO pressiona Enter
        time.sleep(0.3)
        pyautogui.screenshot().save("screenshot.png")
        result = _gemini_analyze_screenshot(contact, message, "screenshot.png", stage="before_send")
        _print_gemini_result(result, player)
        if not result.get("approved"):
            return failed(
                "whatsapp_web",
                f"Gemini não confirmou contato e mensagem. Nada foi enviado. Divergências: {result.get('problems', [])}",
                contact=contact,
            )
        return _store_pending_send(contact, message, {"method": "pyautogui"}, player)
    except _GeminiVerificationError as exc:
        return failed("whatsapp_web", f"verificação Gemini falhou; nada foi enviado: {exc}", contact=contact)
    except Exception as exc:
        return failed("whatsapp_web", f"preparação GUI falhou; nada foi enviado: {exc}", contact=contact)


def _run_playwright_send(contact: str, message: str, player=None, timeout_s: float = 45.0) -> str:
    """Compatibilidade: agora prepara e verifica; o envio aguarda confirmação."""
    return _prepare_playwright_send(contact, message, player=player, timeout_s=timeout_s)


def _run_gui_send(contact: str, message: str, player=None, open_first: bool = True) -> str:
    """Compatibilidade: prepara e verifica; não envia antes da confirmação."""
    return _prepare_gui_send(contact, message, player=player)


def _confirm_pending_send(
    token: str,
    *,
    contact: str,
    message: str,
    confirmed: bool,
    player=None,
) -> str:
    """Confirma um rascunho previamente verificado e verifica visualmente o pós-envio."""
    _expire_pending_sends()
    if not confirmed:
        return ask(
            "whatsapp_web",
            "O envio continua bloqueado. Confirme explicitamente antes de prosseguir.",
            status="awaiting_confirmation",
            contact=contact,
        )
    state = _PENDING_SENDS.pop(token, None)
    if state is None:
        return failed(
            "whatsapp_web",
            "confirmação inválida ou expirada. Prepare a mensagem novamente para uma nova análise.",
            contact=contact,
        )
    if state.get("contact") != contact or state.get("message") != message:
        _close_pending_state(state)
        return failed(
            "whatsapp_web",
            "contato ou mensagem não corresponde ao rascunho aprovado. Nada foi enviado.",
            contact=contact,
        )

    try:
        if state.get("method") == "playwright":
            page = state["page"]
            page.bring_to_front()
            page.screenshot(path="screenshot.png")
            precheck = _gemini_analyze_screenshot(contact, message, "screenshot.png", stage="before_send")
            _print_gemini_result(precheck, player)
            if not precheck.get("approved"):
                return failed(
                    "whatsapp_web",
                    f"a tela mudou e o Gemini não confirmou novamente. Nada foi enviado: {precheck.get('problems', [])}",
                    contact=contact,
                )
            # Único ponto no fluxo Playwright onde Enter é pressionado para enviar.
            page.keyboard.press("Enter")
            time.sleep(1.0)
            page.screenshot(path="screenshot.png")
        elif state.get("method") == "pyautogui":
            pyautogui.screenshot().save("screenshot.png")
            precheck = _gemini_analyze_screenshot(contact, message, "screenshot.png", stage="before_send")
            _print_gemini_result(precheck, player)
            if not precheck.get("approved"):
                return failed(
                    "whatsapp_web",
                    f"a tela mudou e o Gemini não confirmou novamente. Nada foi enviado: {precheck.get('problems', [])}",
                    contact=contact,
                )
            pyautogui.press("enter")
            time.sleep(1.0)
            pyautogui.screenshot().save("screenshot.png")
        else:
            return failed("whatsapp_web", "método de envio pendente desconhecido; nada foi enviado.", contact=contact)

        postcheck = _gemini_analyze_screenshot(contact, message, "screenshot.png", stage="after_send")
        _print_gemini_result(postcheck, player)
        if postcheck.get("approved"):
            return done(
                "whatsapp_web",
                contact=contact,
                status="sent_and_visually_verified",
                verified_by="gemini",
                send_state=postcheck.get("send_state", "sent"),
            )
        return unverified(
            "whatsapp_web",
            "a confirmação foi dada e o comando de envio foi acionado, mas o Gemini não conseguiu confirmar visualmente o resultado. Não repita automaticamente; confira a conversa.",
            contact=contact,
            status="send_unverified",
            problems=postcheck.get("problems", []),
        )
    except _GeminiVerificationError as exc:
        return failed("whatsapp_web", f"verificação Gemini falhou; confira a conversa antes de qualquer novo envio: {exc}", contact=contact)
    except Exception as exc:
        return unverified(
            "whatsapp_web",
            f"ocorreu um erro após a confirmação; confira a conversa para evitar envio duplicado: {exc}",
            contact=contact,
            status="send_result_unknown",
        )
    finally:
        _close_pending_state(state)

def _run_gui_search(contact: str, player=None, open_first: bool = True) -> str:
    if not _PYAUTOGUI:
        return failed(
            "whatsapp_web",
            "PyAutoGUI não instalado — não é possível focar a caixa de pesquisa",
            contact=contact,
        )
    if open_first:
        if not _open_whatsapp_url():
            return failed(
                "whatsapp_web",
                "não foi possível abrir https://web.whatsapp.com",
                contact=contact,
            )
        _wait_gui_settle(5.5, player)
    try:
        _search_and_open_contact_gui(contact, player)
    except Exception as exc:
        return failed("whatsapp_web", f"pesquisa GUI falhou: {exc}", contact=contact)
    return unverified(
        "whatsapp_web",
        "contato pesquisado e Enter pressionado; confirme se a conversa abriu",
        contact=contact,
        status="searched",
        method="pyautogui",
    )


def _normalize_params(params: dict) -> dict:
    p = dict(params or {})
    mode = (p.get("mode") or p.get("action") or "").strip().lower()
    contact = (
        p.get("contact")
        or p.get("receiver")
        or p.get("to")
        or p.get("name")
        or ""
    )
    contact = str(contact).strip()
    message = (
        p.get("message")
        or p.get("message_text")
        or p.get("text")
        or p.get("body")
        or ""
    )
    message = str(message).strip()
    if not mode:
        if contact and message:
            mode = "send"
        elif contact and not message:
            mode = "send"
        else:
            mode = "open"
    return {
        "mode": mode,
        "contact": contact,
        "message": message,
        "confirmation_token": str(p.get("confirmation_token") or "").strip(),
        "confirmed": p.get("confirmed") is True,
    }


def whatsapp_web(
    parameters: Optional[dict] = None,
    player=None,
    session_memory=None,
    **_ctx: Any,
) -> str:
    try:
        p = _normalize_params(parameters if isinstance(parameters, dict) else {})
        mode = p["mode"]
        contact = p["contact"]
        message = p["message"]

        _log(player, f"whatsapp_web mode={mode} contact={contact!r} msg_len={len(message)}")

        if mode in ("confirm_send", "confirmar_envio"):
            if not contact or not message or not p["confirmation_token"]:
                return failed(
                    "whatsapp_web",
                    "para confirmar, informe o token pendente, contato e mensagem exatos.",
                    contact=contact or None,
                )
            return _confirm_pending_send(
                p["confirmation_token"],
                contact=contact,
                message=message,
                confirmed=p["confirmed"],
                player=player,
            )

        if mode in ("open", "abrir", "launch"):
            ok = _open_whatsapp_url()
            if not ok:
                return failed(
                    "whatsapp_web",
                    "não foi possível abrir o navegador em https://web.whatsapp.com",
                )
            if contact and message:
                return _do_send(contact, message, player)
            if contact:
                return ask(
                    "whatsapp_web",
                    f"WhatsApp Web aberto. Qual mensagem você quer enviar para {contact}?",
                    contact=contact,
                    status="opened",
                )
            return ask(
                "whatsapp_web",
                "WhatsApp Web aberto. Para qual contato você quer enviar a mensagem?",
                status="opened",
            )

        if mode in ("search_contact", "search", "pesquisar", "open_chat"):
            if not contact:
                ok = _open_whatsapp_url()
                if not ok:
                    return failed(
                        "whatsapp_web",
                        "não foi possível abrir https://web.whatsapp.com",
                    )
                return ask(
                    "whatsapp_web",
                    "WhatsApp Web aberto. Para qual contato você quer pesquisar?",
                    status="opened",
                )
            return _run_gui_search(contact, player=player, open_first=True)

        if mode in ("send", "enviar", "message", ""):
            if not contact:
                ok = _open_whatsapp_url()
                if not ok:
                    return failed(
                        "whatsapp_web",
                        "não foi possível abrir https://web.whatsapp.com",
                    )
                return ask(
                    "whatsapp_web",
                    "WhatsApp Web aberto. Para qual contato você quer enviar a mensagem?",
                    status="opened",
                )
            if not message:
                try:
                    _run_gui_search(contact, player=player, open_first=True)
                except Exception:
                    _open_whatsapp_url()
                return ask(
                    "whatsapp_web",
                    f"Conversa com {contact} pronta (ou WhatsApp aberto). "
                    "Qual é o texto da mensagem?",
                    contact=contact,
                    status="awaiting_message",
                )
            return _do_send(contact, message, player)

        return failed(
            "whatsapp_web",
            f"mode desconhecido: {mode!r}. Use open, search_contact ou send.",
            mode=mode,
        )
    except Exception as exc:
        return failed("whatsapp_web", f"erro inesperado: {exc}")


def _do_send(contact: str, message: str, player=None) -> str:
    if _HAS_PLAYWRIGHT:
        try:
            return _run_playwright_send(contact, message, player=player)
        except _GeminiVerificationError as exc:
            # Falha/recusa do Gemini bloqueia o envio; nunca tente outro caminho para contornar.
            return failed(
                "whatsapp_web",
                f"verificação visual não aprovada; nada foi enviado: {exc}",
                contact=contact,
            )
        except Exception as exc:
            _log(player, f"Playwright indisponível ({exc}); tentando preparação GUI com a mesma verificação Gemini")

    return _run_gui_send(contact, message, player=player, open_first=True)


TOOL = {
    "name": "whatsapp_web",
    "description": (
        "SEMPRE use esta tool quando o usuário mencionar WhatsApp "
        "(ex: 'abre o whatsapp', 'manda um whatsapp', 'manda mensagem no "
        "whatsapp pro João dizendo oi', 'whatsapp para a mãe'). "
        "Abre https://web.whatsapp.com no navegador, pesquisa o contato, prepara "
        "a mensagem, faz verificação visual com Gemini e só envia após confirmação explícita. "
        "Modes: open, search_contact, send (prepara e aguarda confirmação), "
        "confirm_send (envia após confirmação do usuário). Se faltar o nome do "
        "contato, abre o site e pergunta. Se faltar a mensagem, pergunta o "
        "texto. Depois de send, aguarde o usuário; em resposta afirmativa use "
        "confirm_send com o mesmo contact/message, confirmation_token e confirmed=true. "
        "Nunca use confirm_send sem resposta afirmativa explícita. Preferência: Playwright; fallback: pyautogui + atalho "
        "Ctrl+Alt+/ (Cmd+Ctrl+/ no macOS)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {
                "type": "STRING",
                "description": (
                    "open | search_contact | send | confirm_send. "
                    "send prepara e verifica, mas não envia; confirm_send só após confirmação explícita do usuário."
                ),
                "enum": ["open", "search_contact", "send", "confirm_send"],
            },
            "contact": {
                "type": "STRING",
                "description": (
                    "Nome do contato como aparece no WhatsApp "
                    "(ex: João, mãe, Talita). Alias: receiver."
                ),
            },
            "receiver": {
                "type": "STRING",
                "description": "Alias legado de contact.",
            },
            "message": {
                "type": "STRING",
                "description": "Texto da mensagem a enviar. Alias: message_text.",
            },
            "message_text": {
                "type": "STRING",
                "description": "Alias legado de message.",
            },
            "confirmation_token": {
                "type": "STRING",
                "description": "Token retornado pelo pedido de confirmação anterior; obrigatório em confirm_send.",
            },
            "confirmed": {
                "type": "BOOLEAN",
                "description": "True somente se o usuário respondeu afirmativamente ao pedido de confirmação do WhatsApp.",
            },
        },
        "required": [],
    },
    "handler": whatsapp_web,
    "tier": "core",
    "risk": "destructive",
}
