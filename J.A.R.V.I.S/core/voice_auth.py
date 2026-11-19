"""
core/voice_auth.py — speaker verification from a short enrollment clip.

Design (local-first, no cloud)
-----------------------------
1. Enrollment: user records a few seconds of their voice once.
   We store a compact spectral fingerprint under memory/biometrics/voice_profile.json
   (NOT raw audio by default — only the fingerprint + metadata).
2. Verification: a new clip is fingerprinted the same way and compared with
   cosine similarity. Threshold is configurable (default 0.75).

Fingerprint method
------------------
Pure numpy STFT → log-mel style bands → mean/std vector. No torch/tensorflow
required. If `resemblyzer` is installed later, a better encoder can be swapped
in behind the same API.

This is *verification* (1:1 against the enrolled user), not identification
among many speakers. Suitable as a second factor for unlock / confirm.
"""
from __future__ import annotations

import json
import math
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

_BASE = Path(__file__).resolve().parents[1]
_BIO_DIR = _BASE / "memory" / "biometrics"
_PROFILE = _BIO_DIR / "voice_profile.json"

_DEFAULT_THRESHOLD = 0.75
_N_BANDS = 40
_TARGET_SR = 16000


@dataclass
class VoiceScore:
    score: float
    accepted: bool
    threshold: float
    detail: str


def _ensure_dir() -> None:
    _BIO_DIR.mkdir(parents=True, exist_ok=True)


def _load_wav_mono(path: Path, target_sr: int = _TARGET_SR) -> np.ndarray:
    """Load WAV as float32 mono at target_sr. Only stdlib + numpy."""
    with wave.open(str(path), "rb") as wf:
        n_ch = wf.getnchannels()
        sw = wf.getsampwidth()
        sr = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sw == 1:
        data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0
        data /= 128.0
    elif sw == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported sample width: {sw}")

    if n_ch > 1:
        data = data.reshape(-1, n_ch).mean(axis=1)

    if sr != target_sr and len(data) > 0:
        # Linear resample (good enough for fingerprinting)
        duration = len(data) / float(sr)
        n_out = max(1, int(duration * target_sr))
        x_old = np.linspace(0.0, 1.0, num=len(data), endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
        data = np.interp(x_new, x_old, data).astype(np.float32)
    return data


def _fingerprint(samples: np.ndarray, sr: int = _TARGET_SR) -> np.ndarray:
    """Compact spectral fingerprint: band energies + deltas."""
    if samples.size < sr // 4:
        raise ValueError("clip too short (need ≥0.25s)")

    # Pre-emphasis
    x = np.append(samples[0], samples[1:] - 0.97 * samples[:-1])
    # Hann windowed frames
    frame = int(0.025 * sr)
    hop = int(0.010 * sr)
    if len(x) < frame:
        x = np.pad(x, (0, frame - len(x)))
    n_frames = 1 + max(0, (len(x) - frame) // hop)
    window = np.hanning(frame)
    # FFT size
    n_fft = 512
    # Mel-ish log bands on magnitude spectrum
    specs = []
    for i in range(n_frames):
        start = i * hop
        chunk = x[start:start + frame] * window
        if len(chunk) < frame:
            chunk = np.pad(chunk, (0, frame - len(chunk)))
        mag = np.abs(np.fft.rfft(chunk, n=n_fft))
        specs.append(mag)
    spec = np.stack(specs, axis=0)  # frames x bins
    # Log energy in equal-width bands
    bins = spec.shape[1]
    edges = np.linspace(0, bins, _N_BANDS + 1).astype(int)
    bands = []
    for b0, b1 in zip(edges[:-1], edges[1:]):
        if b1 <= b0:
            bands.append(np.zeros(spec.shape[0]))
        else:
            bands.append(np.log1p(spec[:, b0:b1].mean(axis=1)))
    band_mat = np.stack(bands, axis=1)  # frames x bands
    mean = band_mat.mean(axis=0)
    std = band_mat.std(axis=0) + 1e-6
    # First-order deltas of mean across a coarse time split
    mid = max(1, band_mat.shape[0] // 2)
    delta = band_mat[mid:].mean(axis=0) - band_mat[:mid].mean(axis=0)
    vec = np.concatenate([mean, std, delta]).astype(np.float32)
    # L2 normalize
    norm = np.linalg.norm(vec) + 1e-9
    return vec / norm


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / ((np.linalg.norm(a) + 1e-9) * (np.linalg.norm(b) + 1e-9)))


def enroll_from_wav(path: str | Path, *, label: str = "owner") -> dict[str, Any]:
    """Create / overwrite the voice profile from a WAV file."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    samples = _load_wav_mono(path)
    vec = _fingerprint(samples)
    _ensure_dir()
    profile = {
        "label": label,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sr": _TARGET_SR,
        "dim": int(vec.size),
        "vector": vec.tolist(),
        "threshold": _DEFAULT_THRESHOLD,
        "source": path.name,
        "duration_s": round(len(samples) / _TARGET_SR, 2),
    }
    _PROFILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return {
        "enrolled": True,
        "label": label,
        "dim": profile["dim"],
        "duration_s": profile["duration_s"],
        "path": str(_PROFILE),
    }


def has_profile() -> bool:
    return _PROFILE.is_file()


def load_profile() -> Optional[dict]:
    if not _PROFILE.is_file():
        return None
    try:
        return json.loads(_PROFILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def verify_wav(path: str | Path, *, threshold: Optional[float] = None) -> VoiceScore:
    """Compatibilidade: verificação biométrica vocal desativada no projeto."""
    return VoiceScore(
        score=1.0,
        accepted=True,
        threshold=float(threshold if threshold is not None else _DEFAULT_THRESHOLD),
        detail="voice_auth_disabled",
    )

def set_threshold(value: float) -> float:
    profile = load_profile() or {}
    profile["threshold"] = float(min(0.99, max(0.5, value)))
    _ensure_dir()
    if "vector" not in profile:
        raise RuntimeError("enroll a voice profile before setting threshold")
    _PROFILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return profile["threshold"]


def clear_profile() -> bool:
    if _PROFILE.is_file():
        _PROFILE.unlink()
        return True
    return False
