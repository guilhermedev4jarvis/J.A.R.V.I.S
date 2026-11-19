"""
core/redaction.py — strip secrets and obvious PII before logs / LLM context.

Rules of engagement
-------------------
- Never invent redaction that changes tool *behaviour*. Only transform strings
  that are about to be printed, stored in audit logs, or injected into prompts.
- Prefer over-redaction of key-shaped tokens over leaking an API key once.
- The original value is NOT recoverable from the redacted form (one-way).
"""
from __future__ import annotations

import re
from typing import Any, Mapping

# High-signal secret patterns. Order matters: more specific first.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Bearer / API key headers
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.I), r"\1***"),
    (re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([^\s'\"&,;]+)"), r"\1***"),
    (re.compile(r"(?i)(authorization\s*[=:]\s*)([^\s'\"&,;]+)"), r"\1***"),
    # Common cloud key prefixes
    (re.compile(r"\b(sk-[A-Za-z0-9]{20,})\b"), "sk-***"),
    (re.compile(r"\b(AIza[0-9A-Za-z\-_]{20,})\b"), "AIza***"),  # Google
    (re.compile(r"\b(AQ\.[A-Za-z0-9_\-]{20,})\b"), "AQ.***"),  # Google AI Studio / Gemini
    (re.compile(r"\b(xox[baprs]-[0-9A-Za-z-]{10,})\b"), "xox***"),  # Slack
    (re.compile(r"\b(ghp_[A-Za-z0-9]{20,})\b"), "ghp_***"),
    (re.compile(r"\b(github_pat_[A-Za-z0-9_]{20,})\b"), "github_pat_***"),
    # JWT-ish
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"), "jwt***"),
    # AWS access key id
    (re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), "AKIA***"),
    # Private key blocks
    (re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        re.S,
    ), "-----BEGIN PRIVATE KEY-----***-----END PRIVATE KEY-----"),
    # Password assignments
    (re.compile(r"(?i)(password\s*[=:]\s*)([^\s'\"&,;]+)"), r"\1***"),
    (re.compile(r"(?i)(passwd\s*[=:]\s*)([^\s'\"&,;]+)"), r"\1***"),
    (re.compile(r"(?i)(secret\s*[=:]\s*)([^\s'\"&,;]+)"), r"\1***"),
    (re.compile(r"(?i)(token\s*[=:]\s*)([^\s'\"&,;]+)"), r"\1***"),
]

# Soft PII — optional, controlled by flag
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,3}\)?[-.\s]?)?\d{3,5}[-.\s]?\d{4}\b")
_CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")  # BR CPF-ish


def redact_text(text: str, *, pii: bool = False) -> str:
    """Return a copy of *text* with secrets (and optionally PII) masked."""
    if not text:
        return text
    out = str(text)
    for pattern, repl in _PATTERNS:
        out = pattern.sub(repl, out)
    if pii:
        out = _EMAIL_RE.sub("[email]", out)
        out = _CPF_RE.sub("[cpf]", out)
        # Phone last — aggressive; only when pii=True
        out = _PHONE_RE.sub("[phone]", out)
    return out


def redact_mapping(data: Mapping[str, Any], *, pii: bool = False) -> dict[str, Any]:
    """Deep-ish redaction of string values in a dict (one level + nested dicts)."""
    out: dict[str, Any] = {}
    for k, v in data.items():
        key_l = str(k).lower()
        if key_l in {"password", "token", "secret", "api_key", "apikey", "authorization"}:
            out[k] = "***"
            continue
        if isinstance(v, str):
            out[k] = redact_text(v, pii=pii)
        elif isinstance(v, dict):
            out[k] = redact_mapping(v, pii=pii)
        elif isinstance(v, list):
            out[k] = [
                redact_text(i, pii=pii) if isinstance(i, str)
                else (redact_mapping(i, pii=pii) if isinstance(i, dict) else i)
                for i in v
            ]
        else:
            out[k] = v
    return out


def safe_log(message: str, *, pii: bool = False) -> str:
    """Convenience wrapper for print/logging sites."""
    return redact_text(message, pii=pii)
