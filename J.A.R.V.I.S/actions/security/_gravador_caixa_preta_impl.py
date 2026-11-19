
"""gravador_caixa_preta — gravação ambiente silenciosa em blocos."""
from __future__ import annotations
import threading, time, wave
from datetime import datetime
from pathlib import Path
from typing import Any
from core.outcome import done, failed
from ._security_vision import audit, send_telegram, speak_short

_BASE = Path(__file__).resolve().parents[2]
_DIR = _BASE / "memory" / "audit" / "gravacoes"
_state: dict[str, Any] = {"thread": None, "stop": threading.Event()}
_CHUNK_SEC = 300  # 5 min
_SR = 16000

def _loop(player=None):
    _DIR.mkdir(parents=True, exist_ok=True)
    while not _state["stop"].is_set():
        try:
            import sounddevice as sd
            import numpy as np
            frames = int(_SR * _CHUNK_SEC)
            # record in smaller slices so stop is responsive
            buf = []
            slice_sec = 5
            n_slices = max(1, _CHUNK_SEC // slice_sec)
            for _ in range(n_slices):
                if _state["stop"].is_set():
                    break
                data = sd.rec(int(_SR * slice_sec), samplerate=_SR, channels=1, dtype="float32")
                sd.wait()
                buf.append(data)
            if not buf:
                continue
            audio = np.concatenate(buf, axis=0)
            path = _DIR / f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(_SR)
                pcm = (audio[:, 0] * 32767).astype("int16").tobytes()
                wf.writeframes(pcm)
            send_telegram(f"Caixa-preta: bloco gravado `{path.name}`", str(path))
            audit("blackbox_chunk", tool="gravador_caixa_preta", extra={"file": path.name})
        except Exception as e:
            audit("blackbox_err", tool="gravador_caixa_preta", extra={"error": str(e)[:140]})
            time.sleep(3)

def run(parameters=None, player=None, **_ctx) -> str:
    action = str((parameters or {}).get("action") or "status").lower()
    if action in ("start", "ativar", "gravar"):
        if _state["thread"] and _state["thread"].is_alive():
            return done("gravador_caixa_preta", running=True, already=True)
        _state["stop"] = threading.Event()
        t = threading.Thread(target=_loop, args=(player,), daemon=True, name="caixa-preta")
        _state["thread"] = t
        t.start()
        # no TTS for stealth unless explicitly wanted - short confirm only if player path
        return done("gravador_caixa_preta", action="start", running=True)
    if action in ("stop", "parar"):
        _state["stop"].set()
        if _state.get("thread"):
            _state["thread"].join(timeout=3)
        return done("gravador_caixa_preta", action="stop", running=False)
    return done("gravador_caixa_preta", running=bool(_state["thread"] and _state["thread"].is_alive()))
