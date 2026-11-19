"""Salva/restaura layouts em config/window_workspaces.json."""
from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

from core.outcome import ask, done, failed

def _project_root() -> Path:
    here = Path(__file__).resolve().parent
    for p in [here, *here.parents]:
        if (p / "config").is_dir() and ((p / "core").is_dir() or (p / "main").exists()):
            return p
    return Path(__file__).resolve().parents[3]

def _cfg_path() -> Path:
    return _project_root() / "config" / "window_workspaces.json"



def _load() -> dict:
    if not _cfg_path().exists():
        return {"profiles": {}}
    try:
        data = json.loads(_cfg_path().read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"profiles": {}}
        data.setdefault("profiles", {})
        return data
    except Exception:
        return {"profiles": {}}


def _save(data: dict) -> None:
    _cfg_path().parent.mkdir(parents=True, exist_ok=True)
    _cfg_path().write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _snapshot_windows() -> list[dict[str, Any]]:
    if platform.system() != "Windows":
        return [{"title": "demo", "x": 0, "y": 0, "w": 800, "h": 600, "app": "stub"}]
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        handles: list[dict[str, Any]] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _enum(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    handles.append({
                        "title": buf.value,
                        "x": int(rect.left),
                        "y": int(rect.top),
                        "w": int(rect.right - rect.left),
                        "h": int(rect.bottom - rect.top),
                    })
            return True

        user32.EnumWindows(_enum, 0)
        return handles[:40]
    except Exception as e:
        return [{"error": str(e)[:120]}]


def run(parameters=None, **_ctx) -> str:
    params = dict(parameters or {})
    action = str(params.get("action") or params.get("mode") or "listar_perfis").strip().lower()
    name = str(params.get("name") or params.get("profile") or "").strip()
    data = _load()
    profiles = data.setdefault("profiles", {})
    if action in ("listar_perfis", "list", "listar"):
        return done("organizador_janelas_perfil", profiles=list(profiles.keys()), count=len(profiles))
    if action in ("salvar_perfil", "save", "salvar"):
        if not name:
            return ask("organizador_janelas_perfil", "Qual nome do perfil?")
        snap = _snapshot_windows()
        profiles[name] = {"windows": snap}
        _save(data)
        return done("organizador_janelas_perfil", action="salvar_perfil", profile=name, windows=len(snap))
    if action in ("aplicar_perfil", "apply", "restaurar"):
        if not name:
            return ask("organizador_janelas_perfil", "Qual perfil aplicar?")
        if name not in profiles:
            return failed("organizador_janelas_perfil", f"perfil não encontrado: {name}", available=list(profiles.keys()))
        return done(
            "organizador_janelas_perfil",
            action="aplicar_perfil",
            profile=name,
            windows=profiles[name].get("windows") or [],
            message="Layout carregado.",
        )
    return failed("organizador_janelas_perfil", f"ação desconhecida: {action}")
