"""audio_channel — estado persistente casa / telegram / hibrido."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional

from core.outcome import done, ask
from actions.security._security_vision import audit, speak_short

_BASE = Path(__file__).resolve().parents[2]
_STATE_PATH = _BASE / "memory" / "audio_channel_state.json"
_lock = threading.Lock()
_VALID = frozenset({"casa", "telegram", "hibrido"})

# Runtime flags consumed by main loop / telegram (best-effort)
_runtime: dict[str, Any] = {
    "local_mic_enabled": True,
    "telegram_audio_enabled": True,
    "mode": "hibrido",
}


def _load() -> dict:
    if not _STATE_PATH.is_file():
        return {"mode": "hibrido"}
    try:
        data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"mode": "hibrido"}
    except Exception:
        return {"mode": "hibrido"}


def _save(mode: str) -> None:
    with _lock:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(
            json.dumps({"mode": mode}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def get_mode() -> str:
    m = str(_load().get("mode") or "hibrido").lower()
    return m if m in _VALID else "hibrido"


def local_mic_enabled() -> bool:
    return get_mode() in ("casa", "hibrido")


def telegram_audio_enabled() -> bool:
    return get_mode() in ("telegram", "hibrido")


def apply_mode(mode: str, player=None) -> dict:
    mode = (mode or "").lower().strip()
    if mode in ("rua", "celular", "telegram", "remote"):
        mode = "telegram"
    if mode in ("casa", "home", "local", "cell"):
        # "cell" user said /audio_cell as house - map carefully
        mode = "casa"
    if mode in ("hibrido", "hybrid", "both"):
        mode = "hibrido"
    if mode not in _VALID:
        return {"ok": False, "reason": "invalid_mode"}

    _save(mode)
    _runtime["mode"] = mode
    _runtime["local_mic_enabled"] = mode in ("casa", "hibrido")
    _runtime["telegram_audio_enabled"] = mode in ("telegram", "hibrido")

    # Best-effort: ensure AudioRelay when returning to house modes
    if mode in ("casa", "hibrido"):
        try:
            import main as main_mod
            fn = getattr(main_mod, "_ensure_audiorelay_running", None)
            if callable(fn):
                fn()
        except Exception as e:
            audit("audio_channel_audiorelay", tool="audio_channel", extra={"error": str(e)[:120]})

    phrases = {
        "casa": "Áudio na casa reativado, Senhor. Microfone local em escuta.",
        "telegram": "Modo rua. Microfone local pausado. Respondo apenas pelo Telegram.",
        "hibrido": "Modo híbrido. Casa e Telegram ativos, Senhor.",
    }
    # Only speak on local speakers if local path is active
    speak_short(phrases[mode], player=player, silent=(mode == "telegram"))
    audit("audio_channel_set", tool="audio_channel", extra={"mode": mode})
    return {"ok": True, "mode": mode, **{k: _runtime[k] for k in ("local_mic_enabled", "telegram_audio_enabled")}}


def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or p.get("mode") or "status").lower()
    mode = str(p.get("mode") or "").lower()

    if action in ("status", "get"):
        m = get_mode()
        return done(
            "audio_channel",
            action="status",
            mode=m,
            local_mic_enabled=m in ("casa", "hibrido"),
            telegram_audio_enabled=m in ("telegram", "hibrido"),
        )

    if action in _VALID or action in ("rua", "set", "casa", "telegram", "hibrido"):
        target = mode or action
        if target == "set":
            target = mode
        if target == "rua":
            target = "telegram"
        r = apply_mode(target, player=player)
        if r.get("ok"):
            return done("audio_channel", action="set", **r)
        return ask("audio_channel", "Escolha casa, telegram ou híbrido, Senhor.")

    blob = " ".join(str(v) for v in p.values()).lower()
    if any(x in blob for x in ("rua", "telegram", "celular", "pausar microfone")):
        return done("audio_channel", action="set", **apply_mode("telegram", player=player))
    if any(x in blob for x in ("casa", "alto-falante", "audiorelay", "voltar áudio")):
        return done("audio_channel", action="set", **apply_mode("casa", player=player))
    if "híbrid" in blob or "hibrid" in blob:
        return done("audio_channel", action="set", **apply_mode("hibrido", player=player))

    return ask("audio_channel", "Modo casa, rua (Telegram) ou híbrido, Senhor?")
