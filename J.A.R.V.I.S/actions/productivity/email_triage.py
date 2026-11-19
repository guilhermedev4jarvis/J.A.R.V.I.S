"""
email_triage — summarise recent Gmail messages when OAuth is configured.

If Google credentials are not set up, returns a clear failed status with
setup instructions instead of inventing emails.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.outcome import done, failed

_BASE = Path(__file__).resolve().parents[2]
_TOKEN = _BASE / "config" / "gmail_token.json"
_CREDS = _BASE / "config" / "gmail_credentials.json"


def _try_gmail(max_results: int = 8) -> tuple[list[dict] | None, str | None]:
    """Return (messages, error)."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return None, (
            "Google API libraries not installed. "
            "pip install google-api-python-client google-auth-oauthlib"
        )

    if not _TOKEN.exists() and not _CREDS.exists():
        return None, (
            "Gmail is not connected. Place OAuth client credentials at "
            "config/gmail_credentials.json and complete the sign-in flow "
            "from the settings panel (or existing gmail plugin)."
        )

    try:
        creds = None
        if _TOKEN.exists():
            creds = Credentials.from_authorized_user_file(str(_TOKEN), [
                "https://www.googleapis.com/auth/gmail.readonly",
            ])
        if not creds or not creds.valid:
            return None, (
                "Gmail token missing or expired. Re-authenticate via the "
                "Gmail / Google settings in the app."
            )
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        resp = service.users().messages().list(
            userId="me", maxResults=max_results, labelIds=["INBOX"]
        ).execute()
        messages = []
        for item in resp.get("messages", []):
            msg = service.users().messages().get(
                userId="me", id=item["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {
                h["name"]: h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            messages.append({
                "id": item["id"],
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", "(no subject)"),
                "date": headers.get("Date", ""),
                "snippet": (msg.get("snippet") or "")[:200],
            })
        return messages, None
    except Exception as e:
        return None, f"Gmail API error: {e}"


def email_triage(parameters=None, **_ctx) -> str:
    params = parameters or {}
    max_results = int(params.get("max_results") or 8)
    max_results = max(1, min(max_results, 20))
    query = (params.get("query") or "").strip()

    messages, err = _try_gmail(max_results)
    if err:
        return failed("email_triage", err)

    if query:
        q = query.lower()
        messages = [
            m for m in messages
            if q in (m["subject"] + m["from"] + m["snippet"]).lower()
        ]

    if not messages:
        return done("email_triage", count=0, note="inbox has no matching messages")

    lines = []
    for i, m in enumerate(messages[:max_results], 1):
        lines.append(
            f"{i}. From={m['from'][:60]} | Subject={m['subject'][:80]} | "
            f"Date={m['date'][:30]} | Snippet={m['snippet'][:120]}"
        )

    return done(
        "email_triage",
        count=len(messages),
        messages=" || ".join(lines),
        note=(
            "Prioritise by urgency and sender importance. "
            "Do not invent emails that are not listed."
        ),
    )


TOOL = {
    "name": "email_triage",
    "description": (
        "Reads recent Gmail inbox messages (subject, sender, snippet) when "
        "Google OAuth is configured. Use when the user asks to check email, "
        "triage the inbox, or summarise unread mail. "
        "If Gmail is not connected the tool reports that clearly instead of "
        "guessing."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "max_results": {
                "type": "NUMBER",
                "description": "How many messages to fetch (1–20, default 8).",
            },
            "query": {
                "type": "STRING",
                "description": "Optional filter applied to subject/from/snippet.",
            },
        },
        "required": [],
    },
    "handler": email_triage,
    "tier": "extra",
}
