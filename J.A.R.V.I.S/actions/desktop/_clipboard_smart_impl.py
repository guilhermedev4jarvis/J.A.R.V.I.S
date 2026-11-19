"""
clipboard_smart — read / transform the system clipboard.

Daily-use tool: summarise, translate, clean, or extract from whatever is
currently on the clipboard. Never invents content that is not there.
"""
from __future__ import annotations

import platform
import re
from typing import Optional

from core.outcome import done, failed, unverified
from core.lazyimport import LazyModule, installed

_PYPERCLIP = installed("pyperclip")
pyperclip = LazyModule("pyperclip")

_OS = platform.system()


def _get_text() -> tuple[Optional[str], Optional[str]]:
    """Return (text, error_reason)."""
    if not _PYPERCLIP:
        # Fallbacks without pyperclip
        try:
            if _OS == "Windows":
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                CF_UNICODETEXT = 13
                user32.OpenClipboard(0)
                try:
                    handle = user32.GetClipboardData(CF_UNICODETEXT)
                    if not handle:
                        return "", None
                    size = kernel32.GlobalSize(handle)
                    ptr = kernel32.GlobalLock(handle)
                    try:
                        data = ctypes.wstring_at(ptr)
                        return data or "", None
                    finally:
                        kernel32.GlobalUnlock(handle)
                finally:
                    user32.CloseClipboard()
            elif _OS == "Darwin":
                import subprocess
                r = subprocess.run(
                    ["pbpaste"], capture_output=True, text=True, timeout=5
                )
                return (r.stdout or ""), None
            else:
                import subprocess
                for cmd in (["xclip", "-selection", "clipboard", "-o"],
                            ["xsel", "--clipboard", "--output"],
                            ["wl-paste"]):
                    try:
                        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                        if r.returncode == 0:
                            return (r.stdout or ""), None
                    except FileNotFoundError:
                        continue
                return None, "no clipboard tool available (install xclip/xsel/wl-paste or pyperclip)"
        except Exception as e:
            return None, f"clipboard read failed: {e}"
    try:
        text = pyperclip.paste()
        return (text if isinstance(text, str) else str(text or "")), None
    except Exception as e:
        return None, f"clipboard read failed: {e}"


def _set_text(text: str) -> Optional[str]:
    """Write text to clipboard. Returns error reason or None."""
    if _PYPERCLIP:
        try:
            pyperclip.copy(text)
            return None
        except Exception as e:
            return str(e)
    try:
        if _OS == "Darwin":
            import subprocess
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=5)
            return None
        if _OS == "Linux":
            import subprocess
            for cmd in (["xclip", "-selection", "clipboard"],
                        ["xsel", "--clipboard", "--input"],
                        ["wl-copy"]):
                try:
                    subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=5)
                    return None
                except FileNotFoundError:
                    continue
            return "no clipboard write tool available"
        if _OS == "Windows":
            import subprocess
            # PowerShell Set-Clipboard is reliable for Unicode
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
                input=text.encode("utf-8"),
                check=True,
                timeout=10,
                creationflags=0x08000000,
            )
            return None
    except Exception as e:
        return str(e)
    return "clipboard write not supported on this platform"


def _summarise(text: str, max_chars: int = 400) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    # Prefer cutting at sentence boundary
    cut = text[:max_chars]
    for sep in (". ", "! ", "? ", "\n"):
        i = cut.rfind(sep)
        if i > max_chars // 2:
            return cut[: i + 1].strip() + " …"
    return cut.rstrip() + " …"


def _extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s<>\"']+", text)


def _extract_emails(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)


def clipboard_smart(parameters=None, **_ctx) -> str:
    params = parameters or {}
    action = (params.get("action") or "read").strip().lower()
    target_lang = (params.get("language") or "").strip()
    replace = bool(params.get("replace_clipboard", False))

    text, err = _get_text()
    if err:
        return failed("clipboard_smart", err)
    if text is None:
        return failed("clipboard_smart", "could not read clipboard")
    text = text.strip()
    if not text and action != "read":
        return failed("clipboard_smart", "clipboard is empty")

    if action in ("read", "show", "get"):
        preview = _summarise(text, 500) if text else "(empty)"
        return done(
            "clipboard_smart",
            action="read",
            length=len(text),
            preview=preview,
            empty=(len(text) == 0),
        )

    if action in ("summarise", "summarize", "summary"):
        summary = _summarise(text, 350)
        if replace:
            werr = _set_text(summary)
            if werr:
                return unverified("clipboard_smart", werr, action="summarise", summary=summary)
        return done("clipboard_smart", action="summarise", summary=summary, length=len(text))

    if action in ("clean", "strip", "normalize"):
        cleaned = re.sub(r"[ \t]+", " ", text)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        if replace:
            werr = _set_text(cleaned)
            if werr:
                return unverified("clipboard_smart", werr, action="clean")
        return done(
            "clipboard_smart",
            action="clean",
            length_before=len(text),
            length_after=len(cleaned),
            preview=_summarise(cleaned, 300),
        )

    if action in ("urls", "extract_urls", "links"):
        urls = _extract_urls(text)
        return done("clipboard_smart", action="urls", count=len(urls), urls="; ".join(urls[:20]) or "(none)")

    if action in ("emails", "extract_emails"):
        emails = _extract_emails(text)
        return done(
            "clipboard_smart",
            action="emails",
            count=len(emails),
            emails="; ".join(emails[:20]) or "(none)",
        )

    if action in ("count", "stats"):
        words = len(re.findall(r"\S+", text))
        lines = text.count("\n") + (1 if text else 0)
        return done(
            "clipboard_smart",
            action="stats",
            chars=len(text),
            words=words,
            lines=lines,
        )

    if action in ("translate_hint", "translate"):
        # The model does the actual translation; we only expose content + target.
        # Returning the full text lets the model translate in the next turn.
        preview = text if len(text) < 2000 else text[:2000] + " …"
        return done(
            "clipboard_smart",
            action="translate_hint",
            target_language=target_lang or "user language",
            content=preview,
            length=len(text),
            note="Translate this content into the target language and speak the result.",
        )

    if action in ("write", "set", "copy"):
        new_text = (params.get("text") or "").strip()
        if not new_text:
            return failed("clipboard_smart", "text parameter is required for write")
        werr = _set_text(new_text)
        if werr:
            return failed("clipboard_smart", werr, action="write")
        return done("clipboard_smart", action="write", length=len(new_text))

    return failed(
        "clipboard_smart",
        f"unknown action '{action}'",
        allowed="read, summarise, clean, urls, emails, count, translate_hint, write",
    )


_LEGACY_TOOL = {
    "name": "clipboard_smart",
    "description": (
        "Reads or transforms the system clipboard. Use when the user asks what "
        "is on the clipboard, to summarise/clean it, extract links or emails, "
        "or to put text onto the clipboard. "
        "Actions: read, summarise, clean, urls, emails, count, translate_hint, write. "
        "For translate_hint the model should translate the returned content itself. "
        "Set replace_clipboard=true to write the result back to the clipboard."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "One of: read, summarise, clean, urls, emails, count, "
                    "translate_hint, write"
                ),
            },
            "language": {
                "type": "STRING",
                "description": "Target language for translate_hint (optional).",
            },
            "text": {
                "type": "STRING",
                "description": "Text to put on the clipboard when action=write.",
            },
            "replace_clipboard": {
                "type": "BOOLEAN",
                "description": "If true, write the transformed result back to the clipboard.",
            },
        },
        "required": ["action"],
    },
    "handler": clipboard_smart,
    "tier": "core",
}
