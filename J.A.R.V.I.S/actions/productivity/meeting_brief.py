"""
meeting_brief — prepare a short briefing for an upcoming calendar event.

Uses Google Calendar when credentials exist; otherwise returns a clear failure
and still offers a template the model can fill from memory / user context.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.outcome import done, failed

_BASE = Path(__file__).resolve().parents[2]
_TOKEN = _BASE / "config" / "gmail_token.json"  # often shared with Calendar scopes
_CAL_TOKEN = _BASE / "config" / "calendar_token.json"


def _calendar_events(hours_ahead: int = 12, max_results: int = 6):
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return None, "Google API libraries not installed"

    token_path = _CAL_TOKEN if _CAL_TOKEN.exists() else _TOKEN
    if not token_path.exists():
        return None, (
            "Google Calendar is not connected. Add OAuth credentials and grant "
            "calendar.readonly scope."
        )

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), [
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/gmail.readonly",
        ])
        if not creds or not creds.valid:
            return None, "Calendar token missing or expired — re-authenticate."

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=hours_ahead)
        resp = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = []
        for ev in resp.get("items", []):
            start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date")
            events.append({
                "summary": ev.get("summary") or "(no title)",
                "start": start,
                "location": ev.get("location") or "",
                "description": (ev.get("description") or "")[:300],
                "attendees": [
                    a.get("email", "")
                    for a in (ev.get("attendees") or [])[:8]
                ],
            })
        return events, None
    except Exception as e:
        return None, f"Calendar API error: {e}"


def meeting_brief(parameters=None, **_ctx) -> str:
    params = parameters or {}
    hours = int(params.get("hours_ahead") or 12)
    hours = max(1, min(hours, 72))
    query = (params.get("query") or params.get("title") or "").strip().lower()

    events, err = _calendar_events(hours_ahead=hours)
    if err:
        return failed(
            "meeting_brief",
            err,
            hint=(
                "You can still brief the user from memory or by asking them "
                "for the meeting details."
            ),
        )

    if query:
        events = [
            e for e in events
            if query in (e["summary"] + e["description"] + e["location"]).lower()
        ]

    if not events:
        return done(
            "meeting_brief",
            count=0,
            note=f"no events in the next {hours} hours",
        )

    lines = []
    for i, e in enumerate(events, 1):
        attendees = ", ".join(e["attendees"][:5]) or "(none listed)"
        lines.append(
            f"{i}. {e['summary']} | start={e['start']} | "
            f"location={e['location'] or 'n/a'} | attendees={attendees} | "
            f"notes={e['description'][:120] or 'n/a'}"
        )

    return done(
        "meeting_brief",
        count=len(events),
        events=" || ".join(lines),
        note=(
            "Build a concise verbal briefing: purpose, people, prior context "
            "from memory if any, and suggested talking points. "
            "Do not invent attendees or agenda items that are not listed."
        ),
    )


TOOL = {
    "name": "meeting_brief",
    "description": (
        "Fetches upcoming Google Calendar events and returns structured facts "
        "for a meeting briefing. Use when the user asks to prepare for a "
        "meeting, what is next on the calendar, or a briefing for a specific "
        "event title. Requires Calendar OAuth; otherwise reports that clearly."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "hours_ahead": {
                "type": "NUMBER",
                "description": "How many hours ahead to look (default 12, max 72).",
            },
            "query": {
                "type": "STRING",
                "description": "Optional filter on event title/description.",
            },
            "title": {"type": "STRING", "description": "Alias for query."},
        },
        "required": [],
    },
    "handler": meeting_brief,
    "tier": "extra",
}
