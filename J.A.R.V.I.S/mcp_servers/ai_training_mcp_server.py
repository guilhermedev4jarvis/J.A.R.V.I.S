#!/usr/bin/env python3
"""AI training / Ollama / GPU metrics MCP server for JARVIS."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_servers._mcp_stdio import serve  # noqa: E402

_BASE = Path(__file__).resolve().parents[1]
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _ollama_host() -> str:
    return (os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")


def _datasets_dir() -> Path:
    p = Path(os.getenv("TRAINING_DATASETS_DIR") or "memory/datasets")
    if not p.is_absolute():
        p = _BASE / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def _models_dir() -> Path:
    p = Path(os.getenv("TRAINING_MODELS_DIR") or "memory/models")
    if not p.is_absolute():
        p = _BASE / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def _publish(event: str, **payload) -> None:
    try:
        sys.path.insert(0, str(_BASE))
        from core.event_bus import publish

        publish(event, **payload)
    except Exception:
        pass


def train_list_jobs(_args: dict) -> dict:
    with _LOCK:
        return {"jobs": list(_JOBS.values())}


def train_start_job(args: dict) -> dict:
    script = args.get("script") or args.get("command")
    name = args.get("name") or f"job-{uuid.uuid4().hex[:8]}"
    if not script:
        # default: list datasets as dry-run "job"
        job = {
            "id": name,
            "status": "completed",
            "mode": "dry_run",
            "datasets": [p.name for p in _datasets_dir().iterdir()] if _datasets_dir().exists() else [],
            "started_at": time.time(),
            "finished_at": time.time(),
        }
        with _LOCK:
            _JOBS[name] = job
        _publish("ai.training_completed", job_id=name, mode="dry_run")
        return job
    log_path = _models_dir() / f"{name}.log"
    try:
        proc = subprocess.Popen(
            script if isinstance(script, list) else ["bash", "-lc", str(script)],
            cwd=str(_BASE),
            stdout=open(log_path, "w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    job = {
        "id": name,
        "status": "running",
        "pid": proc.pid,
        "log": str(log_path),
        "started_at": time.time(),
    }
    with _LOCK:
        _JOBS[name] = job
    _publish("ai.training_started", job_id=name, pid=proc.pid)

    def _watch():
        code = proc.wait()
        with _LOCK:
            _JOBS[name]["status"] = "completed" if code == 0 else "failed"
            _JOBS[name]["exit_code"] = code
            _JOBS[name]["finished_at"] = time.time()
        _publish("ai.training_completed", job_id=name, exit_code=code)

    threading.Thread(target=_watch, daemon=True).start()
    return job


def train_stop_job(args: dict) -> dict:
    jid = args.get("job_id") or args.get("id") or args.get("name")
    with _LOCK:
        job = _JOBS.get(str(jid) or "")
    if not job:
        return {"ok": False, "error": "job_not_found"}
    pid = job.get("pid")
    if pid:
        try:
            os.kill(int(pid), 15)
        except Exception as e:
            return {"ok": False, "error": str(e)[:120]}
    with _LOCK:
        job["status"] = "stopped"
    return {"ok": True, "job_id": jid}


def train_gpu_metrics(_args: dict) -> dict:
    out: dict = {"gpu": [], "python_cuda_procs": []}
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.total,temperature.gpu,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
        for line in (r.stdout or "").splitlines():
            parts = [x.strip() for x in line.split(",")]
            if len(parts) >= 6:
                out["gpu"].append(
                    {
                        "index": parts[0],
                        "name": parts[1],
                        "mem_used_mb": parts[2],
                        "mem_total_mb": parts[3],
                        "temp_c": parts[4],
                        "util_pct": parts[5],
                    }
                )
    except Exception as e:
        out["nvidia_smi_error"] = str(e)[:120]
    try:
        r = subprocess.run(["ps", "-eo", "pid,comm,rss"], capture_output=True, text=True, timeout=5)
        for line in (r.stdout or "").splitlines():
            if "python" in line.lower() or "ollama" in line.lower():
                out["python_cuda_procs"].append(line.strip())
    except Exception:
        pass
    return out


def train_list_local_models(_args: dict) -> dict:
    models = {"ollama": [], "checkpoints": []}
    try:
        import urllib.request

        with urllib.request.urlopen(_ollama_host() + "/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models["ollama"] = [m.get("name") for m in data.get("models") or []]
    except Exception as e:
        models["ollama_error"] = str(e)[:120]
    md = _models_dir()
    if md.is_dir():
        models["checkpoints"] = [p.name for p in md.iterdir() if p.is_file() or p.is_dir()]
    return models


TOOLS = {
    "train_list_jobs": {"description": "Lista jobs de treino rastreados.", "inputSchema": {"type": "object", "properties": {}}},
    "train_start_job": {
        "description": "Inicia job de treino/script ou dry-run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "script": {"type": "string"},
            },
        },
    },
    "train_stop_job": {
        "description": "Para job pelo id.",
        "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}},
    },
    "train_gpu_metrics": {"description": "Métricas GPU/VRAM e processos.", "inputSchema": {"type": "object", "properties": {}}},
    "train_list_local_models": {"description": "Modelos Ollama e checkpoints locais.", "inputSchema": {"type": "object", "properties": {}}},
}


def main() -> None:
    serve(
        TOOLS,
        {
            "train_list_jobs": train_list_jobs,
            "train_start_job": train_start_job,
            "train_stop_job": train_stop_job,
            "train_gpu_metrics": train_gpu_metrics,
            "train_list_local_models": train_list_local_models,
        },
    )


if __name__ == "__main__":
    main()
