"""Record meeting audio, transcribe (Whisper if available), save structured note."""
from __future__ import annotations

import json
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.outcome import ask, done, failed, started

_BASE = Path(__file__).resolve().parents[2]
_OUT = Path.home() / ".jarvis" / "meetings"
_state = {"recording": False, "stop": None}
_lock = threading.Lock()


def _record(path: Path, seconds: float, sr: int = 16000) -> Path:
    import numpy as np
    import sounddevice as sd
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(seconds * sr)
    audio = sd.rec(frames, samplerate=sr, channels=1, dtype="float32")
    sd.wait()
    pcm = (audio.reshape(-1) * 32767.0).clip(-32768, 32767).astype("int16")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return path


def _transcribe(path: Path) -> str:
    # Prefer project whisper provider
    try:
        from providers import stt_whisper
        if hasattr(stt_whisper, "transcribe"):
            return str(stt_whisper.transcribe(str(path)) or "")
        if hasattr(stt_whisper, "transcribe_file"):
            return str(stt_whisper.transcribe_file(str(path)) or "")
    except Exception:
        pass
    try:
        import whisper  # type: ignore
        model = whisper.load_model("base")
        result = model.transcribe(str(path))
        return str(result.get("text") or "")
    except Exception as e:
        return f"(transcription unavailable: {e})"


def _summarize(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    joined = " ".join(lines) if lines else text.strip()
    # Heuristic action items
    actions = []
    for sent in re_split(joined):
        low = sent.lower()
        if any(k in low for k in ("action", "todo", "tarefa", "prazo", "deadline", "vamos", "preciso")):
            actions.append(sent[:200])
    return {
        "summary": " ".join(re_split(joined)[:6]) or "(empty)",
        "action_items": actions[:8],
        "chars": len(joined),
    }


def re_split(text: str) -> list[str]:
    import re
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _save_note(title: str, transcript: str, meta: dict, player=None) -> str:
    try:
        from .quick_note import quick_note
        body = (
            f"# {title}\n\n## Summary\n{meta.get('summary')}\n\n"
            f"## Action items\n" +
            ("\n".join(f"- {a}" for a in meta.get("action_items") or []) or "- (none)") +
            f"\n\n## Transcript\n{transcript[:8000]}\n"
        )
        return quick_note({"action": "add", "text": body, "notebook": "meetings"}, player=player)
    except Exception as e:
        out = _OUT / f"{title}.md"
        _OUT.mkdir(parents=True, exist_ok=True)
        out.write_text(f"# {title}\n\n{transcript}\n", encoding="utf-8")
        return f"saved:{out} err:{e}"


def run(parameters: Optional[dict] = None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or p.get("mode") or "record").strip().lower()
    seconds = float(p.get("seconds") or p.get("duration") or 30)
    seconds = max(5.0, min(seconds, 600.0))
    title = str(p.get("title") or p.get("name") or datetime.now().strftime("meeting_%Y%m%d_%H%M%S")).strip()

    if action in ("status",):
        return done("meeting_transcriber", recording=bool(_state.get("recording")))

    if action in ("record", "start", "capture"):
        with _lock:
            if _state.get("recording"):
                return failed("meeting_transcriber", "already recording")
            _state["recording"] = True

        def _bg():
            try:
                wav = _OUT / f"{title}.wav"
                _OUT.mkdir(parents=True, exist_ok=True)
                _record(wav, seconds)
                transcript = _transcribe(wav)
                meta = _summarize(transcript)
                _save_note(title, transcript, meta, player=player)
                print(f"[meeting] saved {title} chars={meta.get('chars')}")
            except Exception as e:
                print(f"[meeting] failed: {e}")
            finally:
                with _lock:
                    _state["recording"] = False

        threading.Thread(target=_bg, daemon=True, name="meeting-rec").start()
        return started("meeting_transcriber", op="record", title=title, seconds=seconds)

    if action in ("transcribe_file", "file"):
        path = str(p.get("path") or "").strip()
        if not path:
            return ask("meeting_transcriber", "Qual o caminho do áudio da reunião?")
        wp = Path(path).expanduser()
        if not wp.is_file():
            return failed("meeting_transcriber", "audio file not found", path=path)
        transcript = _transcribe(wp)
        meta = _summarize(transcript)
        _save_note(title, transcript, meta, player=player)
        return done("meeting_transcriber", op="transcribe_file", title=title, **meta)

    return failed("meeting_transcriber", f"unknown action {action}")
