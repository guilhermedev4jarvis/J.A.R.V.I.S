
"""Auditoria de credenciais com k-anonymity (HIBP) e analise local de forca."""
from __future__ import annotations

import hashlib
import math
import re
import string
from typing import Any

from core.outcome import ask, done, failed

try:
    import requests
except Exception:
    requests = None  # type: ignore


def _mask(s: str) -> str:
    if not s:
        return "***"
    if len(s) <= 2:
        return "**"
    return s[0] + ("*" * min(8, len(s) - 2)) + s[-1]


def _sha1_hex(password: str) -> str:
    return hashlib.sha1(password.encode("utf-8", errors="replace")).hexdigest().upper()


def _hibp_range(prefix5: str, timeout: float = 8.0) -> list[str] | None:
    if requests is None:
        return None
    url = f"https://api.pwnedpasswords.com/range/{prefix5}"
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "JARVIS-Security-Audit"})
        if r.status_code != 200:
            return None
        return r.text.splitlines()
    except Exception:
        return None


def _entropy_bits(password: str) -> float:
    if not password:
        return 0.0
    pool = 0
    if any(c.islower() for c in password):
        pool += 26
    if any(c.isupper() for c in password):
        pool += 26
    if any(c.isdigit() for c in password):
        pool += 10
    if any(c in string.punctuation for c in password):
        pool += len(string.punctuation)
    if pool <= 1:
        pool = len(set(password)) or 1
    return round(len(password) * math.log2(pool), 2)


def _weak_patterns(password: str) -> list[str]:
    issues = []
    low = password.lower()
    if len(password) < 8:
        issues.append("muito_curta")
    if re.fullmatch(r"\d+", password):
        issues.append("somente_digitos")
    if low in {"password", "123456", "qwerty", "admin", "senha", "jarvis"}:
        issues.append("comum_dicionario")
    if re.search(r"(.)\1{3,}", password):
        issues.append("repeticao")
    if re.search(r"(0123|1234|2345|abcd|qwer)", low):
        issues.append("sequencia")
    return issues


def _check_password(password: str) -> dict[str, Any]:
    digest = _sha1_hex(password)
    prefix, suffix = digest[:5], digest[5:]
    lines = _hibp_range(prefix)
    count = 0
    online = False
    if lines is not None:
        online = True
        for line in lines:
            parts = line.split(":")
            if len(parts) >= 2 and parts[0].strip().upper() == suffix:
                try:
                    count = int(parts[1].strip())
                except ValueError:
                    count = 1
                break
    return {
        "pwned_count": count,
        "breached": count > 0,
        "online_check": online,
        "sha1_prefix": prefix,
        "masked": _mask(password),
        "entropy_bits": _entropy_bits(password),
        "weak_patterns": _weak_patterns(password),
    }


def _email_local_hints(email: str) -> dict[str, Any]:
    email = email.strip()
    ok_fmt = bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))
    return {
        "masked": _mask(email),
        "format_ok": ok_fmt,
        "note": "Verificacao de vazamento de e-mail requer API externa configurada; analise local de formato apenas.",
    }


def run(parameters=None, **_ctx) -> str:
    params = dict(parameters or {})
    mode = str(params.get("mode") or params.get("action") or "verificar_senha").strip().lower()
    secret = str(params.get("password") or params.get("senha") or params.get("value") or "").strip()
    email = str(params.get("email") or "").strip()

    if mode in ("verificar_senha", "check_password", "senha"):
        if not secret:
            return ask("auditor_vazamento_credenciais", "Informe a senha a auditar (nao sera logada em claro).")
        result = _check_password(secret)
        # never echo password
        return done("auditor_vazamento_credenciais", mode=mode, **result)

    if mode in ("auditar_forca", "forca", "strength"):
        if not secret:
            return ask("auditor_vazamento_credenciais", "Informe a senha para auditar forca.")
        bits = _entropy_bits(secret)
        weak = _weak_patterns(secret)
        score = "fraca" if bits < 40 or weak else ("media" if bits < 60 else "forte")
        return done(
            "auditor_vazamento_credenciais",
            mode=mode,
            entropy_bits=bits,
            weak_patterns=weak,
            score=score,
            masked=_mask(secret),
        )

    if mode in ("verificar_email", "email"):
        if not email:
            return ask("auditor_vazamento_credenciais", "Informe o e-mail.")
        return done("auditor_vazamento_credenciais", mode=mode, **_email_local_hints(email))

    return failed("auditor_vazamento_credenciais", f"mode desconhecido: {mode}")
