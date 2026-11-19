"""Análise e limpeza segura de caches/temporários."""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any

from core.outcome import ask, done, failed


def _dir_size(path: Path, limit_files: int = 8000) -> tuple[int, int]:
    total = 0
    count = 0
    if not path.exists():
        return 0, 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                fp = Path(root) / name
                try:
                    total += fp.stat().st_size
                    count += 1
                except OSError:
                    continue
                if count >= limit_files:
                    return total, count
    except OSError:
        pass
    return total, count


def _targets() -> list[dict[str, Any]]:
    home = Path.home()
    items = [
        ("user_temp", Path(tempfile.gettempdir())),
        ("pip_cache", home / ".cache" / "pip"),
        ("pytest_cache", home / ".pytest_cache"),
        ("localapp_temp", home / "AppData" / "Local" / "Temp"),
    ]
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windir:
        items.append(("windows_temp", Path(windir) / "Temp"))
    out = []
    for label, path in items:
        size, n = _dir_size(path)
        out.append({
            "id": label,
            "path": str(path),
            "bytes": size,
            "mb": round(size / (1024 * 1024), 2),
            "files_sampled": n,
            "exists": path.exists(),
        })
    return out


def _safe_clean(path: Path) -> tuple[int, int]:
    removed = 0
    freed = 0
    if not path.exists():
        return 0, 0
    cutoff = time.time() - 2 * 86400
    for root, _dirs, files in os.walk(path):
        for name in files:
            fp = Path(root) / name
            try:
                st = fp.stat()
                if st.st_mtime > cutoff or not fp.is_file():
                    continue
                sz = st.st_size
                fp.unlink(missing_ok=True)
                removed += 1
                freed += sz
            except OSError:
                continue
    return removed, freed


def run(parameters=None, **_ctx) -> str:
    params = dict(parameters or {})
    mode = str(params.get("mode") or params.get("action") or "analisar").strip().lower()
    targets = _targets()
    total_mb = round(sum(t["mb"] for t in targets), 2)
    if mode in ("analisar", "analyze", "scan", "report"):
        return done(
            "limpeza_profunda_disco",
            mode="analisar",
            total_mb=total_mb,
            targets=targets,
            message=f"Potencial liberável ~{total_mb} MB. Nada foi apagado.",
        )
    if mode in ("limpar", "clean", "purge"):
        confirm = str(params.get("confirm") or "").strip().lower() in ("1", "true", "yes", "sim", "confirmar")
        if not confirm:
            return ask(
                "limpeza_profunda_disco",
                "Confirma limpeza de temporários com mais de 2 dias? confirm=sim",
                total_mb=total_mb,
                targets=targets,
            )
        report = []
        freed_total = 0
        for t in targets:
            if t["id"] not in ("user_temp", "windows_temp", "localapp_temp", "pip_cache", "pytest_cache"):
                continue
            n, freed = _safe_clean(Path(t["path"]))
            freed_total += freed
            report.append({"id": t["id"], "removed_files": n, "freed_mb": round(freed / (1024 * 1024), 2)})
        return done(
            "limpeza_profunda_disco",
            mode="limpar",
            freed_mb=round(freed_total / (1024 * 1024), 2),
            details=report,
        )
    return failed("limpeza_profunda_disco", f"mode desconhecido: {mode}")
