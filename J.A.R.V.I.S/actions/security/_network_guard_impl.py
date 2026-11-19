"""
network_guard — alerts de rede enquanto você joga.

Mede periodicamente:
  - latência (ping a 1.1.1.1 / 8.8.8.8)
  - throughput aproximado (bytes enviados/recebidos via psutil)
  - se a conexão caiu

Intervalo adaptativo:
  - rede boa     → ~20 min (configurável)
  - rede fraca   → mais frequente
  - crítica/offline → bem mais frequente

Não mexe em processos de jogo; só observa e reporta.
Estado em config/network_guard.json.
"""
from __future__ import annotations

import json
import platform
import socket
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from core.outcome import done, failed, ask, started

_BASE = Path(__file__).resolve().parents[2]
_STATE_PATH = _BASE / "config" / "network_guard.json"
_lock = threading.Lock()

_worker: threading.Thread | None = None
_stop_event = threading.Event()
_runtime: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "last_sample": None,
    "last_alert": None,
    "alerts": 0,
    "samples": 0,
}

# thresholds (ms / Mbps-ish)
_LAT_GOOD = 60
_LAT_FAIR = 120
_LAT_POOR = 200
# throughput in KB/s observed on interfaces (not a speed test — traffic sample)
_THR_POOR_KB = 50      # very low activity can be normal when idle; we mainly care latency + drops
_INTERVAL_GOOD = 20 * 60
_INTERVAL_FAIR = 10 * 60
_INTERVAL_POOR = 3 * 60
_INTERVAL_CRIT = 60


def _has_psutil() -> bool:
    try:
        import psutil  # noqa: F401
        return True
    except ImportError:
        return False


def _load() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "interval_good_sec": _INTERVAL_GOOD,
            "last_level": None,
            "history": [],
        }


def _save(data: dict) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _STATE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _ping_ms(host: str = "1.1.1.1", timeout_sec: float = 2.0) -> float | None:
    """Return RTT in ms or None on failure."""
    system = platform.system()
    try:
        if system == "Windows":
            cmd = ["ping", "-n", "1", "-w", str(int(timeout_sec * 1000)), host]
        else:
            cmd = ["ping", "-c", "1", "-W", str(int(timeout_sec)), host]
        kw: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "timeout": timeout_sec + 1.5,
        }
        if system == "Windows":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        proc = subprocess.run(cmd, **kw)
        out = (proc.stdout or "") + (proc.stderr or "")
        # parse time=XXXms or time<1ms
        import re
        m = re.search(r"time[=<]([\d.]+)\s*ms", out, re.I)
        if m:
            return float(m.group(1))
        if proc.returncode != 0:
            return None
        return None
    except Exception:
        return None


def _tcp_latency_ms(host: str = "1.1.1.1", port: int = 443, timeout: float = 2.0) -> float | None:
    """Fallback latency via TCP connect timing."""
    try:
        start = time.perf_counter()
        with socket.create_connection((host, port), timeout=timeout):
            pass
        return round((time.perf_counter() - start) * 1000, 1)
    except OSError:
        return None


def _throughput_sample(seconds: float = 1.5) -> dict[str, float]:
    """Approximate KB/s in/out over a short window (interface counters)."""
    if not _has_psutil():
        return {"down_kb_s": 0.0, "up_kb_s": 0.0}
    import psutil
    a = psutil.net_io_counters()
    time.sleep(seconds)
    b = psutil.net_io_counters()
    down = max(0, b.bytes_recv - a.bytes_recv) / seconds / 1024.0
    up = max(0, b.bytes_sent - a.bytes_sent) / seconds / 1024.0
    return {"down_kb_s": round(down, 1), "up_kb_s": round(up, 1)}


def _classify(latency_ms: float | None, thr: dict) -> str:
    if latency_ms is None:
        return "offline"
    if latency_ms >= _LAT_POOR:
        return "critical"
    if latency_ms >= _LAT_FAIR:
        return "poor"
    if latency_ms >= _LAT_GOOD:
        return "fair"
    return "good"


def _interval_for(level: str, base_good: int) -> int:
    return {
        "good": base_good,
        "fair": max(60, base_good // 2),
        "poor": _INTERVAL_POOR,
        "critical": _INTERVAL_CRIT,
        "offline": _INTERVAL_CRIT,
    }.get(level, base_good)


def _human_speed(kb_s: float) -> str:
    if kb_s >= 1024:
        return f"{kb_s / 1024:.1f} MB/s"
    return f"{kb_s:.0f} KB/s"


def _sample_once() -> dict:
    lat = _ping_ms("1.1.1.1")
    if lat is None:
        lat = _ping_ms("8.8.8.8")
    if lat is None:
        lat = _tcp_latency_ms()
    thr = _throughput_sample(1.2)
    level = _classify(lat, thr)
    return {
        "at": datetime.now().isoformat(timespec="seconds"),
        "latency_ms": lat,
        "down_kb_s": thr["down_kb_s"],
        "up_kb_s": thr["up_kb_s"],
        "level": level,
        "message": _format_msg(lat, thr, level),
    }


def _format_msg(lat: float | None, thr: dict, level: str) -> str:
    if level == "offline" or lat is None:
        return "Rede offline ou sem resposta de ping."
    down = _human_speed(thr.get("down_kb_s") or 0)
    up = _human_speed(thr.get("up_kb_s") or 0)
    # Note: down/up here is *current traffic*, not max bandwidth speed test
    if level == "critical":
        return f"Rede crítica: latência {lat:.0f} ms, tráfego ↓{down} ↑{up}."
    if level == "poor":
        return f"Rede fraca: latência {lat:.0f} ms, tráfego ↓{down} ↑{up}."
    if level == "fair":
        return f"Rede ok-ish: latência {lat:.0f} ms, tráfego ↓{down} ↑{up}."
    return f"Rede boa: latência {lat:.0f} ms, tráfego ↓{down} ↑{up}."


def _should_alert(level: str, prev_level: str | None) -> bool:
    """Alert on degradation or while remaining bad; quiet when stable-good."""
    if level in ("offline", "critical", "poor"):
        return True
    if prev_level in ("offline", "critical", "poor") and level in ("fair", "good"):
        return True  # recovery notice
    return False


def _loop(interval_good: int) -> None:
    global _runtime
    _runtime = {
        "running": True,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "last_sample": None,
        "last_alert": None,
        "alerts": 0,
        "samples": 0,
    }
    disk = _load()
    prev_level = disk.get("last_level")
    try:
        while not _stop_event.is_set():
            try:
                sample = _sample_once()
                level = sample["level"]
                with _lock:
                    _runtime["last_sample"] = sample
                    _runtime["samples"] = int(_runtime.get("samples") or 0) + 1

                hist = disk.get("history") or []
                hist.append(sample)
                disk["history"] = hist[-30:]
                disk["last_level"] = level
                _save(disk)

                if _should_alert(level, prev_level):
                    with _lock:
                        _runtime["last_alert"] = sample
                        _runtime["alerts"] = int(_runtime.get("alerts") or 0) + 1
                    # Print is the hook the live session / logs can pick up;
                    # the status tool returns the same text on demand.
                    print(f"[NetworkGuard] ALERT: {sample['message']}")
                prev_level = level

                wait = _interval_for(level, interval_good)
                # sleep in small chunks so stop is responsive
                end = time.time() + wait
                while time.time() < end and not _stop_event.is_set():
                    time.sleep(0.5)
            except Exception as e:
                with _lock:
                    _runtime["last_sample"] = {
                        "level": "error",
                        "message": str(e)[:200],
                        "at": datetime.now().isoformat(timespec="seconds"),
                    }
                time.sleep(30)
    finally:
        with _lock:
            _runtime["running"] = False


def network_guard(parameters: dict | None = None, **_ctx) -> str:
    params = parameters or {}
    action = (params.get("action") or "status").strip().lower()

    # ── status ────────────────────────────────────────────────────────────
    if action in ("status", "report"):
        with _lock:
            rt = dict(_runtime)
        last = rt.get("last_sample") or {}
        alert = rt.get("last_alert") or {}
        return done(
            "network_guard",
            action="status",
            running=bool(rt.get("running")),
            started_at=rt.get("started_at"),
            samples=rt.get("samples") or 0,
            alerts=rt.get("alerts") or 0,
            last_level=last.get("level"),
            last_latency_ms=last.get("latency_ms"),
            last_down=last.get("down_kb_s"),
            last_up=last.get("up_kb_s"),
            last_message=last.get("message"),
            last_alert_message=alert.get("message"),
            note=(
                "Throughput is current interface traffic, not a full speed test. "
                "Latency is the main gaming signal."
            ),
        )

    # ── once (manual check) ───────────────────────────────────────────────
    if action in ("check", "once", "sample"):
        sample = _sample_once()
        return done(
            "network_guard",
            action="check",
            level=sample["level"],
            latency_ms=sample["latency_ms"],
            down_kb_s=sample["down_kb_s"],
            up_kb_s=sample["up_kb_s"],
            message=sample["message"],
        )

    # ── start ─────────────────────────────────────────────────────────────
    if action in ("start", "watch", "guard", "on"):
        global _worker
        if _runtime.get("running") and _worker and _worker.is_alive():
            return failed("network_guard", "already running — stop first or use status")

        try:
            interval = int(params.get("interval_sec") or params.get("interval") or _INTERVAL_GOOD)
        except (TypeError, ValueError):
            interval = _INTERVAL_GOOD
        interval = max(60, min(interval, 3600))

        disk = _load()
        disk["interval_good_sec"] = interval
        _save(disk)

        _stop_event.clear()
        _worker = threading.Thread(
            target=_loop,
            args=(interval,),
            name="jarvis-network-guard",
            daemon=True,
        )
        _worker.start()
        return started(
            "network_guard",
            interval_good_sec=interval,
            note=(
                f"Watching network while you play. Good net → check every ~{interval // 60} min; "
                "poor/critical → more often. Alerts print when quality drops. action=stop to end."
            ),
        )

    # ── stop ──────────────────────────────────────────────────────────────
    if action in ("stop", "off", "halt"):
        was = bool(_runtime.get("running"))
        _stop_event.set()
        if _worker and _worker.is_alive():
            _worker.join(timeout=3.0)
        with _lock:
            _runtime["running"] = False
        return done(
            "network_guard",
            action="stop",
            was_running=was,
            note="network guard stopped" if was else "was not running",
        )

    return ask(
        "network_guard",
        "what should I do?",
        options="start (interval_sec=1200), stop, status, check",
    )


_LEGACY_TOOL = {
    "name": "network_guard",
    "description": (
        "Monitors network quality while gaming and alerts when latency gets bad "
        "or the link drops. Adaptive interval: ~20 minutes when the net is good, "
        "much more often when poor/offline. "
        "Reports latency (ping) and current traffic rates. "
        "Actions: start (optional interval_sec), stop, status, check (one-shot sample). "
        "Use when the user is playing and wants to be warned about lag or packet issues."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "start | stop | status | check",
            },
            "interval_sec": {
                "type": "NUMBER",
                "description": "Seconds between checks when network is good (default 1200 = 20 min)",
            },
        },
        "required": [],
    },
    "handler": network_guard,
    "tier": "core",
}
