
"""offline — flag global, bloqueio de rede externa, prepare Ollama/Piper."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

from core.outcome import done, ask
from core.resilience import atomic_write_json, safe_read_json

_BASE = Path(__file__).resolve().parents[2]
_STATE = _BASE / "memory" / "offline_state.json"
_lock = threading.Lock()
OLLAMA_MODEL = os.getenv("OFFLINE_OLLAMA_MODEL", "qwen2.5:7b")
PIPER_VOICE = os.getenv("OFFLINE_PIPER_VOICE", "pt_BR-faber-medium")


def _load() -> dict:
    data = safe_read_json(_STATE, default={"offline": False})
    return data if isinstance(data, dict) else {"offline": False}


def _save(data: dict) -> None:
    with _lock:
        atomic_write_json(_STATE, data)


def is_offline() -> bool:
    return bool(_load().get("offline"))


def set_offline(value: bool) -> dict:
    data = _load()
    data["offline"] = bool(value)
    data["llm"] = "ollama" if value else data.get("llm_online", "auto")
    data["stt"] = "whisper_local" if value else "auto"
    data["tts"] = "piper" if value else "auto"
    _save(data)
    # notify network_fallback / llm
    try:
        from core import network_fallback as nf
        if hasattr(nf, "set_force_local"):
            nf.set_force_local(bool(value))
        else:
            os.environ["JARVIS_FORCE_LOCAL"] = "1" if value else "0"
            if hasattr(nf, "reset_cache"):
                nf.reset_cache()
    except Exception:
        os.environ["JARVIS_FORCE_LOCAL"] = "1" if value else "0"
    try:
        from core import mcp_client as mcp
        if hasattr(mcp, "apply_offline_policy"):
            mcp.apply_offline_policy(bool(value))
    except Exception:
        pass
    return data


def prepare_offline_stack() -> dict:
    report: dict[str, Any] = {"ollama_model": OLLAMA_MODEL, "piper_voice": PIPER_VOICE}
    # Ollama model
    try:
        if shutil.which("ollama"):
            r = subprocess.run(
                ["ollama", "pull", OLLAMA_MODEL],
                capture_output=True,
                text=True,
                timeout=600,
            )
            report["ollama_pull"] = {"code": r.returncode, "out": (r.stdout or r.stderr or "")[-400:]}
        else:
            report["ollama_pull"] = {"ok": False, "reason": "ollama_not_in_path"}
    except Exception as e:
        report["ollama_pull"] = {"ok": False, "error": str(e)[:160]}
    # Piper voice — best-effort path under memory/piper or ~/.local
    try:
        voice_dir = _BASE / "memory" / "piper"
        voice_dir.mkdir(parents=True, exist_ok=True)
        report["piper_dir"] = str(voice_dir)
        # If piper CLI exists, user can download; we record expected names
        report["piper_files_expected"] = [
            f"{PIPER_VOICE}.onnx",
            f"{PIPER_VOICE}.onnx.json",
        ]
        existing = [p.name for p in voice_dir.glob("*.onnx")]
        report["piper_present"] = existing
    except Exception as e:
        report["piper"] = {"error": str(e)[:120]}
    report["ok"] = True
    return report


def run(parameters=None, player=None, **_ctx) -> str:
    from actions.security._security_vision import speak_short
    p = dict(parameters or {})
    action = str(p.get("action") or "status").lower()
    blob = " ".join(str(v) for v in p.values()).lower()

    if action in ("enable", "offline", "bunker") or any(x in blob for x in ("ativar modo offline", "desativar internet", "bunker")):
        if action in ("status",):
            pass
        set_offline(True)
        speak_short(
            "Modo offline ativado, Senhor. Conexões externas bloqueadas e processamento transferido para o servidor local.",
            player=player,
        )
        return done("offline", action="enable", offline=True, state=_load())

    if action in ("disable", "online") or any(x in blob for x in ("desativar modo offline", "ativar internet", "modo online")):
        set_offline(False)
        speak_short("Modo online restaurado, Senhor.", player=player)
        return done("offline", action="disable", offline=False, state=_load())

    if action in ("prepare", "preparar"):
        speak_short("Preparando modelos locais, Senhor.", player=player)
        rep = prepare_offline_stack()
        return done("offline", action="prepare", **rep)

    return done("offline", action="status", offline=is_offline(), state=_load())


def offline_knowledge_answer(query: str) -> dict:
    """When offline, answer from local FTS/BM25 knowledge base."""
    try:
        from core import knowledge_store
        knowledge_store.reindex_all()
        return knowledge_store.answer_with_citations(query)
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}
