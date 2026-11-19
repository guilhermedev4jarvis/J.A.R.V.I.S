"""
agent_mode_control — switch between listen / assist / autonomous and air-gap.
"""
from __future__ import annotations

from core.agent_mode import (
    get_mode,
    set_mode,
    air_gapped,
    set_air_gapped,
    strict_paths,
    set_strict_paths,
    snapshot,
    label_pt,
    validate_feedback_enabled,
    set_validate_feedback,
)
from core.outcome import done, failed, ask


def agent_mode_control(parameters: dict | None = None, **_ctx) -> str:
    params = parameters or {}
    action = str(params.get("action") or "status").strip().lower()

    if action in ("status", "show", "current", ""):
        snap = snapshot()
        return done(
            "agent_mode_control",
            action="status",
            mode=snap.get("mode"),
            label=label_pt(),
            air_gapped=bool(snap.get("air_gapped")),
            strict_paths=bool(snap.get("strict_paths")),
            validate_feedback=bool(snap.get("validate_feedback")),
        )

    if action in ("set", "mode"):
        mode = str(params.get("mode") or "").strip().lower()
        if mode not in {"listen", "assist", "autonomous"}:
            return ask(
                "agent_mode_control",
                "which mode?",
                options="listen | assist | autonomous",
            )
        applied = set_mode(mode)
        return done(
            "agent_mode_control",
            action="set",
            mode=applied,
            label=label_pt(applied),
            note="Mode persisted to config/agent_mode.json",
        )

    if action in ("air_gap", "air_gapped", "offline"):
        val = str(params.get("enabled") or params.get("value") or "true").lower()
        enabled = val in ("1", "true", "yes", "on")
        set_air_gapped(enabled)
        return done("agent_mode_control", action="air_gapped", enabled=enabled)

    if action in ("strict_paths", "paths"):
        val = str(params.get("enabled") or params.get("value") or "true").lower()
        enabled = val in ("1", "true", "yes", "on")
        set_strict_paths(enabled)
        return done("agent_mode_control", action="strict_paths", enabled=enabled)

    if action in ("validate_feedback", "hud_validate"):
        val = str(params.get("enabled") or params.get("value") or "true").lower()
        enabled = val in ("1", "true", "yes", "on")
        set_validate_feedback(enabled)
        return done("agent_mode_control", action="validate_feedback", enabled=enabled)

    return ask(
        "agent_mode_control",
        "what should I change?",
        options="status | set (mode=listen|assist|autonomous) | air_gapped | strict_paths | validate_feedback",
    )


TOOL = {
    "name": "agent_mode_control",
    "description": (
        "Controls JARVIS operating mode: listen (no actuation), assist (default), "
        "autonomous (multi-step agents freer). Also toggles air_gapped (block cloud "
        "tools), strict_paths (sandbox path policy), and validate_feedback (HUD "
        "indicator for Observar→Agir→Validar). Prefer this over guessing settings."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "status | set | air_gapped | strict_paths | validate_feedback",
            },
            "mode": {
                "type": "STRING",
                "description": "listen | assist | autonomous (for action=set)",
            },
            "enabled": {
                "type": "STRING",
                "description": "true|false for toggle actions",
            },
        },
        "required": [],
    },
    "handler": agent_mode_control,
    "tier": "core",
    "risk": "review",
}
