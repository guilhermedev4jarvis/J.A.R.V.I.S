"""Action: browser_pilot - autonomous browser reads and form automation."""
from __future__ import annotations

import importlib
import re
from typing import Any, Optional
from urllib.parse import quote_plus

from core.outcome import ask, done, failed, untrusted


def _load_playwright() -> Any:
    try:
        return importlib.import_module("playwright.sync_api")
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            "playwright nao esta instalado. Execute "
            "'pip install playwright && playwright install chromium'"
        ) from exc


def _clean_url(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    if re.match(r"^https?://", value, re.I):
        return value
    return "https://" + value


def _owner_confirmation(parameters: dict, *, action: str) -> tuple[bool, str]:
    approved = str(parameters.get("confirmed") or parameters.get("approve") or "").lower() in (
        "1", "true", "yes", "sim",
    )
    password = parameters.get("password")
    if not approved and not password:
        return False, "Confirme antes de enviar ou alterar dados no navegador."
    if password:
        try:
            from core.owner_gate import require_owner

            auth = require_owner(
                tool_name="browser_pilot",
                action=action,
                password=str(password),
                text=str(parameters.get("text") or ""),
            )
            if isinstance(auth, dict) and not auth.get("ok"):
                return False, str(auth.get("detail") or "owner_gate denied")
        except Exception as exc:
            return False, f"owner_gate error: {exc}"
    return True, "confirmed"


def _extract_page(page: Any, max_chars: int) -> dict[str, Any]:
    title = str(page.title() or "").strip()
    page.evaluate(
        """
        () => {
          for (const el of document.querySelectorAll(
            'script, style, noscript, nav, header, footer, aside, form, iframe'
          )) el.remove();
        }
        """
    )
    text = str(page.locator("body").inner_text(timeout=8000) or "")
    lines = []
    seen: set[str] = set()
    for line in text.splitlines():
        clean = re.sub(r"\s+", " ", line).strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            lines.append(clean)
    content = "\n".join(lines)
    if max_chars > 0:
        content = content[:max_chars]
    return {"title": title, "url": str(page.url or ""), "content": content}


def _open_browser(sync_api: Any, headless: bool):
    pw = sync_api.sync_playwright().start()
    browser = pw.chromium.launch(headless=headless)
    page = browser.new_page()
    return pw, browser, page


def handler(
    parameters: Optional[dict[str, Any]] = None,
    player: Any = None,
    session_memory: Any = None,
    **ctx: Any,
) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "").strip().lower()
    if action not in {"search_and_summarize", "extract_links", "fill_and_submit"}:
        return ask(
            "browser_pilot",
            "Qual acao o navegador deve executar?",
            action=action or "missing",
            options="search_and_summarize|extract_links|fill_and_submit",
        )

    try:
        sync_api = _load_playwright()
    except RuntimeError as exc:
        return failed("browser_pilot", str(exc), action=action)

    pw = None
    browser = None
    try:
        headless = str(p.get("headless") or "true").lower() not in {"0", "false", "no"}
        pw, browser, page = _open_browser(sync_api, headless=headless)

        if action == "fill_and_submit":
            url = _clean_url(str(p.get("url") or ""))
            if not url:
                return ask("browser_pilot", "Informe a URL do formulario.", action=action)
            fields = p.get("fields")
            if not isinstance(fields, dict) or not fields:
                return ask("browser_pilot", "Informe os campos e valores no objeto fields.", action=action)
            submit = str(p.get("submit") or "true").lower() in {"1", "true", "yes", "sim"}
            if submit:
                ok, detail = _owner_confirmation(p, action="fill_and_submit")
                if not ok:
                    return ask("browser_pilot", detail, action=action)

            page.goto(url, wait_until="domcontentloaded", timeout=int(p.get("timeout_ms") or 30000))
            filled = 0
            for selector, value in fields.items():
                sel = str(selector).strip()
                if not sel:
                    continue
                page.locator(sel).fill(str(value))
                filled += 1
            if submit:
                submit_selector = str(p.get("submit_selector") or "").strip()
                if submit_selector:
                    page.locator(submit_selector).click()
                else:
                    page.keyboard.press("Enter")
                page.wait_for_timeout(500)
            result = {
                "title": str(page.title() or "").strip(),
                "url": str(page.url or ""),
                "filled": filled,
                "submitted": submit,
            }
            return done("browser_pilot", action="fill_and_submit", count=filled,
                        submitted=submit, title=result["title"], url=result["url"])

        url = _clean_url(str(p.get("url") or ""))
        if not url:
            query = str(p.get("query") or "").strip()
            if not query:
                return ask("browser_pilot", "Informe uma URL ou consulta para pesquisar.", action=action)
            url = "https://duckduckgo.com/html/?q=" + quote_plus(query)

        page.goto(url, wait_until="domcontentloaded", timeout=int(p.get("timeout_ms") or 30000))

        if action == "extract_links":
            limit = max(1, min(int(p.get("limit") or 20), 100))
            links = page.evaluate(
                """
                (limit) => Array.from(document.querySelectorAll('a[href]'))
                  .map(a => ({
                    title: (a.innerText || a.getAttribute('title') || '').trim(),
                    href: a.href
                  }))
                  .filter(x => x.title && x.href)
                  .slice(0, limit)
                """,
                limit,
            )
            unique: list[dict[str, str]] = []
            seen: set[str] = set()
            for item in links if isinstance(links, list) else []:
                href = str(item.get("href") or "").strip()
                if href and href not in seen:
                    seen.add(href)
                    unique.append({"title": str(item.get("title") or "").strip(), "href": href})
            payload = untrusted(str(page.url or url), str(unique))
            return done("browser_pilot", action="extract_links", count=len(unique),
                        title=str(page.title() or ""), url=str(page.url or url), links=payload)

        max_chars = max(500, min(int(p.get("max_chars") or 12000), 100000))
        extracted = _extract_page(page, max_chars)
        payload = untrusted(extracted["url"], extracted["content"])
        return done(
            "browser_pilot",
            action="search_and_summarize",
            title=extracted["title"],
            url=extracted["url"],
            chars=len(extracted["content"]),
            content=payload,
        )
    except Exception as exc:
        return failed("browser_pilot", f"browser error: {exc}", action=action)
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                pass


TOOL = {
    "name": "browser_pilot",
    "description": (
        "Autonomous Playwright browser pilot. Searches or opens pages, extracts clean "
        "main text or links, and fills forms. Form submission requires explicit confirmation."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["search_and_summarize", "extract_links", "fill_and_submit"],
            },
            "url": {"type": "STRING"},
            "query": {"type": "STRING"},
            "fields": {"type": "OBJECT", "description": "CSS selector to value mapping"},
            "submit": {"type": "BOOLEAN"},
            "submit_selector": {"type": "STRING"},
            "confirmed": {"type": "BOOLEAN"},
            "password": {"type": "STRING"},
            "headless": {"type": "BOOLEAN"},
            "max_chars": {"type": "INTEGER"},
            "limit": {"type": "INTEGER"},
            "timeout_ms": {"type": "INTEGER"},
        },
        "required": ["action"],
    },
    "handler": handler,
    "tier": "core",
    "risk": "autonomous",
}
