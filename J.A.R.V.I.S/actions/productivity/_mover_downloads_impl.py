"""mover_downloads — busca em Downloads, backup, shutil.move, audit/undo."""
from __future__ import annotations

import os
import re
import shutil
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.outcome import ask, done, failed
from core.resilience import atomic_write_json

_BASE = Path(__file__).resolve().parents[2]
_BACKUP = _BASE / "memory" / "backups"


def _downloads_dir() -> Path:
    """Resolve the real Windows Downloads folder (with common fallbacks)."""
    candidates: list[Path] = []
    home = Path.home()
    candidates.append(home / "Downloads")
    userprofile = os.getenv("USERPROFILE") or os.getenv("HOME")
    if userprofile:
        candidates.append(Path(userprofile) / "Downloads")
    # OneDrive redirected Downloads
    for env_key in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        od = os.getenv(env_key)
        if od:
            candidates.append(Path(od) / "Downloads")
    # Windows known-folder via registry (best-effort)
    if platform.system() == "Windows":
        try:
            import winreg  # type: ignore

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            ) as key:
                val, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
                if val:
                    candidates.insert(0, Path(os.path.expandvars(str(val))))
        except Exception:
            pass
    for c in candidates:
        try:
            if c.is_dir():
                return c
        except Exception:
            continue
    # last resort: create under home
    d = home / "Downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _map_destination(raw: Optional[str]) -> Path:
    text = (raw or "").strip().lower()
    aliases = {
        "": _BASE,
        "root": _BASE,
        "raiz": _BASE,
        "parte principal": _BASE,
        "pasta principal": _BASE,
        "pasta do jarvis": _BASE,
        "jarvis": _BASE,
        "actions": _BASE / "actions",
        "acoes": _BASE / "actions",
        "ações": _BASE / "actions",
        "core": _BASE / "core",
        "nucleo": _BASE / "core",
        "núcleo": _BASE / "core",
        "config": _BASE / "config",
        "configuracoes": _BASE / "config",
        "configurações": _BASE / "config",
        "memory": _BASE / "memory",
        "memoria": _BASE / "memory",
        "memória": _BASE / "memory",
        "providers": _BASE / "providers",
        "desktop": Path.home() / "Desktop",
        "area de trabalho": Path.home() / "Desktop",
        "área de trabalho": Path.home() / "Desktop",
        "documentos": Path.home() / "Documents",
        "documents": Path.home() / "Documents",
    }
    if text in aliases:
        return aliases[text]
    # fuzzy contains
    for key, dest in aliases.items():
        if key and key in text:
            return dest
    # absolute / relative path
    if raw:
        p = Path(raw).expanduser()
        if p.is_absolute():
            return p
        # treat as subdir of project root
        return (_BASE / raw).resolve()
    return _BASE


def _find_in_downloads(filename: str) -> Optional[Path]:
    name = (filename or "").strip()
    if not name:
        return None
    dl = _downloads_dir()
    exact = dl / name
    if exact.is_file():
        return exact
    # case-insensitive partial match → newest mtime
    needle = name.lower()
    matches: list[Path] = []
    try:
        for p in dl.iterdir():
            if not p.is_file():
                continue
            if needle in p.name.lower() or p.name.lower() == needle:
                matches.append(p)
    except Exception:
        return None
    if not matches:
        return None
    matches.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return matches[0]


def _backup_if_exists(dest_file: Path) -> Optional[Path]:
    if not dest_file.exists():
        return None
    _BACKUP.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = _BACKUP / f"{dest_file.name}_backup_{stamp}.bak"
    shutil.copy2(dest_file, bak)
    return bak


def _audit(kind: str, extra: dict) -> None:
    try:
        from core import audit as audit_mod
        audit_mod.log_event(kind, tool="mover_downloads", extra=extra)
    except Exception:
        pass


def _undo_record(src: str, dest: str, backup: Optional[str]) -> None:
    try:
        from core import undo as undo_mod
        if hasattr(undo_mod, "record"):
            undo_mod.record(
                "mover_downloads",
                {"from": dest, "to": src, "backup": backup},
            )
        elif hasattr(undo_mod, "push"):
            undo_mod.push({"tool": "mover_downloads", "from": dest, "to": src, "backup": backup})
    except Exception:
        pass


def _maybe_hot_reload(dest: Path) -> Optional[str]:
    try:
        if dest.suffix.lower() == ".py" and dest.parent.name == "actions":
            import actions.system.hot_reload as hot_reload
            r = hot_reload.hot_reload(parameters={"action": "reload", "name": dest.stem})
            return str(r)[:200]
    except Exception as e:
        return f"hot_reload_skip:{e}"
    return None


def _parse_natural(text: str) -> dict[str, str]:
    """Extract filename + destination hints from free-form Portuguese."""
    low = (text or "").lower()
    if "abrir" in low and "download" in low:
        return {"action": "open_downloads"}
    # destination keywords
    dest = "root"
    for key in (
        "actions", "ações", "acoes", "core", "núcleo", "nucleo", "config",
        "memory", "memória", "memoria", "providers",
        "área de trabalho", "area de trabalho", "desktop",
        "documentos", "documents",
        "raiz", "root", "pasta principal", "pasta do jarvis",
    ):
        if key in low:
            dest = key
            break
    # filename: after 'arquivo', 'pega o', 'move', 'recorta', 'atualiza o'
    fname = ""
    patterns = [
        r"(?:arquivo|move|recorta|pega|atualiza(?:\s+o)?)\s+[\"']?([A-Za-z0-9_.\-]+)[\"']?",
        r"/mover_download\s+(\S+)",
        r"([A-Za-z0-9_\-]+\.[A-Za-z0-9]+)",
    ]
    for pat in patterns:
        m = re.search(pat, text or "", flags=re.I)
        if m:
            fname = m.group(1)
            break
    return {"action": "move", "filename": fname, "destination": dest}


def open_downloads_folder() -> dict:
    dl = _downloads_dir()
    try:
        if platform.system() == "Windows":
            os.startfile(str(dl))  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess_safe = __import__("subprocess")
            subprocess_safe.run(["open", str(dl)], timeout=5)
        else:
            subprocess_safe = __import__("subprocess")
            subprocess_safe.run(["xdg-open", str(dl)], timeout=5)
        return {"ok": True, "path": str(dl)}
    except Exception as e:
        return {"ok": False, "path": str(dl), "error": str(e)[:160]}


def move_file(filename: str, destination: str = "root") -> dict[str, Any]:
    src = _find_in_downloads(filename)
    if not src:
        return {
            "ok": False,
            "reason": "not_found",
            "downloads": str(_downloads_dir()),
            "filename": filename,
        }
    dest_dir = _map_destination(destination)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return {"ok": False, "reason": f"dest_mkdir:{e}", "destination": str(dest_dir)}

    dest_file = dest_dir / src.name
    backup = None
    try:
        backup_path = _backup_if_exists(dest_file)
        if backup_path:
            backup = str(backup_path)
        shutil.move(str(src), str(dest_file))
    except Exception as e:
        return {"ok": False, "reason": f"move_failed:{e}", "src": str(src), "dest": str(dest_file)}

    hr = _maybe_hot_reload(dest_file)
    extra = {
        "src": str(src),
        "dest": str(dest_file),
        "backup": backup,
        "hot_reload": hr,
    }
    _audit("mover_downloads_ok", extra)
    _undo_record(str(src), str(dest_file), backup)
    return {"ok": True, **extra}


def run(parameters=None, player=None, **_ctx) -> str:
    from actions.security._security_vision import speak_short

    p = dict(parameters or {})
    action = str(p.get("action") or "").lower()
    filename = str(p.get("filename") or p.get("name") or "").strip()
    destination = str(p.get("destination") or p.get("dest") or "root").strip()
    text = str(p.get("text") or p.get("query") or "").strip()

    if not action and text:
        parsed = _parse_natural(text)
        action = parsed.get("action") or "move"
        filename = filename or parsed.get("filename") or ""
        destination = destination if destination and destination != "root" else (parsed.get("destination") or "root")

    if action in ("open_downloads", "open"):
        r = open_downloads_folder()
        speak_short("Abrindo a pasta Downloads, Senhor.", player=player)
        return done("mover_downloads", action="open_downloads", **r)

    if action in ("status",):
        return done(
            "mover_downloads",
            action="status",
            downloads=str(_downloads_dir()),
            project_root=str(_BASE),
        )

    # default: move
    if not filename and text:
        parsed = _parse_natural(text)
        filename = parsed.get("filename") or ""
        if parsed.get("destination"):
            destination = parsed["destination"]
    if not filename:
        return ask("mover_downloads", "Qual arquivo dos Downloads devo mover, Senhor?")

    result = move_file(filename, destination)
    if not result.get("ok"):
        speak_short("Não encontrei esse arquivo nos Downloads, Senhor.", player=player)
        return failed("mover_downloads", result.get("reason") or "falha", **result)

    speak_short("Arquivo movido com sucesso, Senhor.", player=player)
    return done("mover_downloads", action="move", **result)
