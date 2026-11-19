"""
audio_latency_tuner — finds a good balance between voice latency and stability.

Measures round-trip characteristics of the audio stack (sounddevice input
latency, suggested buffer sizes) and can persist preferred settings into
config/audio_latency.json so the rest of the pipeline can read them.

Does not change live stream parameters mid-conversation unless explicitly
asked; it mainly diagnoses and stores recommendations.
"""
from __future__ import annotations

import json
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from core.outcome import done, failed, ask

_BASE = Path(__file__).resolve().parents[2]
_STATE_PATH = _BASE / "config" / "audio_latency.json"

# Candidate buffer sizes (frames) commonly useful with 16 kHz / 24 kHz
_CANDIDATE_BUFFERS = [256, 512, 1024, 2048, 4096]
_DEFAULT_RATE = 16000


def _load_state() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "preferred_input_latency_ms": None,
            "preferred_output_latency_ms": None,
            "preferred_blocksize": 1024,
            "sample_rate": _DEFAULT_RATE,
            "last_tune": None,
            "device_notes": {},
        }


def _save_state(data: dict) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _STATE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _has_sounddevice() -> bool:
    try:
        import sounddevice  # noqa: F401
        return True
    except ImportError:
        return False


def _query_devices() -> dict[str, Any]:
    import sounddevice as sd

    hostapis = []
    try:
        for i, api in enumerate(sd.query_hostapis()):
            hostapis.append({
                "index": i,
                "name": api.get("name"),
                "devices": api.get("devices"),
            })
    except Exception:
        pass

    default_in, default_out = sd.default.device
    devices = []
    try:
        for i, d in enumerate(sd.query_devices()):
            devices.append({
                "index": i,
                "name": d.get("name"),
                "max_input_channels": d.get("max_input_channels", 0),
                "max_output_channels": d.get("max_output_channels", 0),
                "default_samplerate": d.get("default_samplerate"),
                "default_low_input_latency": d.get("default_low_input_latency"),
                "default_low_output_latency": d.get("default_low_output_latency"),
                "default_high_input_latency": d.get("default_high_input_latency"),
                "default_high_output_latency": d.get("default_high_output_latency"),
            })
    except Exception as e:
        return {"error": str(e)}

    return {
        "hostapis": hostapis,
        "default_input": default_in,
        "default_output": default_out,
        "devices": devices,
    }


def _measure_latency(blocksize: int = 1024, rate: int = _DEFAULT_RATE) -> dict:
    """
    Best-effort measurement using sounddevice defaults.
    Returns reported low/high latencies; does not open a long stream.
    """
    import sounddevice as sd

    result: dict[str, Any] = {
        "blocksize": blocksize,
        "sample_rate": rate,
    }

    try:
        # Query default device latencies (seconds → ms)
        in_dev = sd.query_devices(kind="input")
        out_dev = sd.query_devices(kind="output")

        result["input_low_ms"] = round(float(in_dev.get("default_low_input_latency", 0) or 0) * 1000, 1)
        result["input_high_ms"] = round(float(in_dev.get("default_high_input_latency", 0) or 0) * 1000, 1)
        result["output_low_ms"] = round(float(out_dev.get("default_low_output_latency", 0) or 0) * 1000, 1)
        result["output_high_ms"] = round(float(out_dev.get("default_high_output_latency", 0) or 0) * 1000, 1)

        # Theoretical buffer latency
        result["buffer_ms"] = round((blocksize / rate) * 1000, 1)

        # Suggested total one-way estimate (buffer + device low)
        result["est_input_ms"] = round(result["buffer_ms"] + result["input_low_ms"], 1)
        result["est_output_ms"] = round(result["buffer_ms"] + result["output_low_ms"], 1)
        result["est_roundtrip_ms"] = round(result["est_input_ms"] + result["est_output_ms"], 1)

    except Exception as e:
        result["error"] = str(e)

    return result


def _recommend(measurements: list[dict]) -> dict:
    """
    Pick a blocksize that keeps estimated round-trip reasonable (< ~120 ms)
    while preferring stability (larger buffers on Windows often help).
    """
    if not measurements:
        return {"blocksize": 1024, "reason": "fallback"}

    # Prefer the largest buffer that still keeps est_roundtrip under 140 ms
    good = [m for m in measurements if m.get("est_roundtrip_ms") and m["est_roundtrip_ms"] <= 140]
    if good:
        best = max(good, key=lambda m: m["blocksize"])
        return {
            "blocksize": best["blocksize"],
            "est_roundtrip_ms": best["est_roundtrip_ms"],
            "reason": "largest stable buffer under 140 ms RT",
        }

    # Otherwise the smallest available
    best = min(measurements, key=lambda m: m.get("est_roundtrip_ms") or 9999)
    return {
        "blocksize": best.get("blocksize", 1024),
        "est_roundtrip_ms": best.get("est_roundtrip_ms"),
        "reason": "lowest estimated latency (still high)",
    }


def audio_latency_tuner(parameters: dict | None = None, **_ctx) -> str:
    params = parameters or {}
    action = (params.get("action") or "status").strip().lower()

    state = _load_state()

    # ── status (works without sounddevice) ────────────────────────────────
    if action in ("status", "report", "current"):
        return done(
            "audio_latency_tuner",
            action="status",
            preferred_blocksize=state.get("preferred_blocksize"),
            preferred_input_latency_ms=state.get("preferred_input_latency_ms"),
            preferred_output_latency_ms=state.get("preferred_output_latency_ms"),
            sample_rate=state.get("sample_rate", _DEFAULT_RATE),
            last_tune=state.get("last_tune"),
            sounddevice_available=_has_sounddevice(),
            note="Use action=tune to measure and recommend optimal settings.",
        )

    # ── set manually (works without sounddevice) ──────────────────────────
    if action in ("auto", "ab", "auto_tune"):
        rate = int(params.get("sample_rate") or state.get("sample_rate") or _DEFAULT_RATE)
        if not _has_sounddevice():
            return failed("audio_latency_tuner", "sounddevice not installed")
        result = _auto_ab(state, rate)
        if not result.get("ok"):
            return failed(
                "audio_latency_tuner",
                "A/B probe failed",
                measurements=str(result.get("measurements")),
            )
        chosen = result["chosen"]
        return done(
            "audio_latency_tuner",
            action="auto",
            applied_blocksize=chosen["blocksize"],
            score=chosen.get("score"),
            note="Best buffer applied to config/audio_latency.json (auto_applied=true).",
        )


    if action in ("set", "apply"):
        try:
            bs = int(params.get("blocksize") or params.get("buffer") or 0)
        except (TypeError, ValueError):
            return failed("audio_latency_tuner", "blocksize must be an integer")
        if bs not in _CANDIDATE_BUFFERS and bs < 128:
            return failed(
                "audio_latency_tuner",
                f"blocksize should be one of {_CANDIDATE_BUFFERS} or >= 128",
            )
        state["preferred_blocksize"] = bs
        if params.get("sample_rate"):
            try:
                state["sample_rate"] = int(params["sample_rate"])
            except (TypeError, ValueError):
                pass
        from datetime import datetime
        state["last_tune"] = datetime.now().isoformat(timespec="seconds")
        _save_state(state)
        return done(
            "audio_latency_tuner",
            action="set",
            preferred_blocksize=bs,
            sample_rate=state.get("sample_rate"),
        )

    # Unknown action — answer before requiring sounddevice
    if action not in ("devices", "list_devices", "measure", "tune", "test", "calibrate"):
        return ask(
            "audio_latency_tuner",
            "what should I do?",
            options="status, devices, tune, set (blocksize=N)",
        )

    # Remaining actions need sounddevice
    if not _has_sounddevice():
        return failed(
            "audio_latency_tuner",
            "sounddevice is not installed — required for latency measurements",
        )

    # ── devices ───────────────────────────────────────────────────────────
    if action in ("devices", "list_devices"):
        info = _query_devices()
        if "error" in info:
            return failed("audio_latency_tuner", info["error"])

        # Compact summary for the model
        ins = [d for d in info["devices"] if d["max_input_channels"] > 0]
        outs = [d for d in info["devices"] if d["max_output_channels"] > 0]
        in_names = "; ".join(f"{d['index']}:{d['name'][:40]}" for d in ins[:8])
        out_names = "; ".join(f"{d['index']}:{d['name'][:40]}" for d in outs[:8])

        return done(
            "audio_latency_tuner",
            action="devices",
            default_input=info["default_input"],
            default_output=info["default_output"],
            input_devices=in_names or "(none)",
            output_devices=out_names or "(none)",
            hostapi_count=len(info.get("hostapis") or []),
        )

    # ── measure / tune ────────────────────────────────────────────────────
    if action in ("measure", "tune", "test", "calibrate"):
        rate = int(params.get("sample_rate") or state.get("sample_rate") or _DEFAULT_RATE)
        measurements = []
        for bs in _CANDIDATE_BUFFERS:
            m = _measure_latency(blocksize=bs, rate=rate)
            measurements.append(m)
            time.sleep(0.05)

        rec = _recommend(measurements)
        # Persist recommendation
        state["preferred_blocksize"] = rec["blocksize"]
        state["sample_rate"] = rate
        # Store the measurement for that blocksize
        chosen = next((m for m in measurements if m["blocksize"] == rec["blocksize"]), {})
        state["preferred_input_latency_ms"] = chosen.get("est_input_ms")
        state["preferred_output_latency_ms"] = chosen.get("est_output_ms")
        state["last_tune"] = datetime.now().isoformat(timespec="seconds")
        state["last_measurements"] = measurements
        _save_state(state)

        summary = "; ".join(
            f"bs={m['blocksize']} rt≈{m.get('est_roundtrip_ms', '?')}ms"
            for m in measurements
        )

        return done(
            "audio_latency_tuner",
            action="tune",
            recommended_blocksize=rec["blocksize"],
            estimated_roundtrip_ms=rec.get("est_roundtrip_ms"),
            reason=rec.get("reason"),
            sample_rate=rate,
            all_measurements=summary,
            note=(
                "Recommendation saved to config/audio_latency.json. "
                "Restart the audio pipeline or call the engine to pick it up."
            ),
        )


def _auto_ab(state: dict, rate: int) -> dict:
    """Lightweight A/B: try two candidate blocksizes and keep the lower estimated RT."""
    candidates = [512, 1024, 2048]
    measurements = []
    for bs in candidates:
        try:
            import sounddevice as sd
            # Opening a short stream is the cheapest real probe we can do.
            t0 = time.perf_counter()
            stream = sd.RawInputStream(samplerate=rate, blocksize=bs, channels=1, dtype="int16")
            stream.start()
            time.sleep(0.05)
            stream.stop()
            stream.close()
            dt_ms = (time.perf_counter() - t0) * 1000.0
            # Prefer smaller buffers unless open cost spikes hard (unstable).
            score = dt_ms + (bs / 64.0)
            measurements.append({"blocksize": bs, "open_ms": round(dt_ms, 1), "score": round(score, 1)})
        except Exception as e:
            measurements.append({"blocksize": bs, "error": str(e), "score": 1e9})
    ok = [m for m in measurements if "error" not in m]
    if not ok:
        return {"ok": False, "measurements": measurements}
    best = min(ok, key=lambda m: m["score"])
    state["preferred_blocksize"] = best["blocksize"]
    state["sample_rate"] = rate
    state["last_tune"] = datetime.now().isoformat(timespec="seconds")
    state["last_ab"] = measurements
    state["auto_applied"] = True
    _save_state(state)
    return {"ok": True, "chosen": best, "measurements": measurements}



TOOL = {
    "name": "audio_latency_tuner",
    "description": (
        "Measures and tunes audio buffer / latency settings for the voice pipeline "
        "(sounddevice + STT + TTS). Finds a good compromise between responsiveness "
        "and stability, then saves the recommendation. "
        "Use when voice feels laggy, choppy, or when setting up audio on a new machine. "
        "Actions: status, devices, tune, auto (A/B apply best buffer), set (blocksize=N)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "status | devices | tune | auto | set",
            },
            "blocksize": {
                "type": "NUMBER",
                "description": "For action=set: buffer size in frames (e.g. 512, 1024, 2048)",
            },
            "sample_rate": {
                "type": "NUMBER",
                "description": "Optional sample rate override (default 16000)",
            },
        },
        "required": [],
    },
    "handler": audio_latency_tuner,
    "tier": "core",
}
