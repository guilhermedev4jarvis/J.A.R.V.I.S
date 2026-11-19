"""
file_organize — sort a folder by type and/or date into subfolders.

Safe by default:
  * Only operates under the user's home directory
  * Dry-run mode unless confirm=true
  * Never touches system folders
  * Uses shutil.move and records enough to undo via core.undo when possible
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from core.outcome import done, failed, ask
from core.undo import push_undo

_HOME = Path.home().resolve()

_TYPE_MAP = {
    "images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".heic", ".svg"},
    "videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v"},
    "audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"},
    "documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv"},
    "archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "code": {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".html", ".css", ".json", ".yml", ".yaml", ".md"},
    "installers": {".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".appimage"},
}


def _classify(path: Path) -> str:
    ext = path.suffix.lower()
    for group, exts in _TYPE_MAP.items():
        if ext in exts:
            return group
    return "other"


def _safe_dir(raw: str) -> Path | None:
    try:
        p = Path(raw).expanduser().resolve()
    except Exception:
        return None
    try:
        p.relative_to(_HOME)
    except ValueError:
        return None
    if not p.exists() or not p.is_dir():
        return None
    return p


def file_organize(parameters=None, **_ctx) -> str:
    params = parameters or {}
    folder = (params.get("folder") or params.get("path") or "").strip()
    mode = (params.get("mode") or "type").strip().lower()  # type | date | type_date
    confirm = bool(params.get("confirm", False))
    limit = int(params.get("limit") or 500)
    limit = max(1, min(limit, 2000))

    if not folder:
        # Sensible default: Downloads
        folder = str(_HOME / "Downloads")

    root = _safe_dir(folder)
    if root is None:
        return failed(
            "file_organize",
            "folder must exist and be inside your home directory",
            folder=folder,
        )

    files = [p for p in root.iterdir() if p.is_file() and not p.name.startswith(".")]
    files = files[:limit]
    if not files:
        return done("file_organize", action="plan", moved=0, note="folder has no files to organise")

    plan: list[tuple[Path, Path]] = []
    for src in files:
        if mode == "date":
            try:
                ts = datetime.fromtimestamp(src.stat().st_mtime)
                sub = root / f"{ts.year}-{ts.month:02d}"
            except Exception:
                sub = root / "unknown_date"
        elif mode == "type_date":
            kind = _classify(src)
            try:
                ts = datetime.fromtimestamp(src.stat().st_mtime)
                sub = root / kind / f"{ts.year}-{ts.month:02d}"
            except Exception:
                sub = root / kind
        else:
            sub = root / _classify(src)
        dest = sub / src.name
        # Avoid overwrite: add suffix
        if dest.exists():
            stem, suf = src.stem, src.suffix
            n = 1
            while dest.exists():
                dest = sub / f"{stem}_{n}{suf}"
                n += 1
        plan.append((src, dest))

    if not confirm:
        sample = "; ".join(f"{s.name} → {d.parent.name}/" for s, d in plan[:12])
        return ask(
            "file_organize",
            f"Ready to move {len(plan)} files in {root}. "
            f"Call again with confirm=true to execute. Sample: {sample}",
            count=len(plan),
            folder=str(root),
            mode=mode,
        )

    moved = 0
    errors = []
    for src, dest in plan:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            # undo: move back
            def _undo(s=src, d=dest):
                if d.exists():
                    s.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(d), str(s))
                    return f"restored {s.name}"
                return f"{d.name} already gone"
            try:
                push_undo(_undo, label=f"organise:{src.name}")
            except Exception:
                pass
            moved += 1
        except Exception as e:
            errors.append(f"{src.name}: {e}")

    if errors and moved == 0:
        return failed("file_organize", "; ".join(errors[:5]), folder=str(root))
    return done(
        "file_organize",
        action="moved",
        moved=moved,
        failed_count=len(errors),
        folder=str(root),
        mode=mode,
        errors="; ".join(errors[:5]) if errors else "",
    )


_LEGACY_TOOL = {
    "name": "file_organize",
    "description": (
        "Organises files inside a folder (default: Downloads) into subfolders "
        "by type and/or date. Only works under the user's home directory. "
        "Always runs as a dry-run first and asks for confirm=true before moving "
        "anything. Modes: type (images/docs/...), date (YYYY-MM), type_date."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "folder": {
                "type": "STRING",
                "description": "Folder to organise (default: ~/Downloads).",
            },
            "path": {"type": "STRING", "description": "Alias for folder."},
            "mode": {
                "type": "STRING",
                "description": "type | date | type_date (default type).",
            },
            "confirm": {
                "type": "BOOLEAN",
                "description": "Must be true to actually move files.",
            },
            "limit": {
                "type": "NUMBER",
                "description": "Max files to process (default 500).",
            },
        },
        "required": [],
    },
    "handler": file_organize,
    "tier": "core",
}
