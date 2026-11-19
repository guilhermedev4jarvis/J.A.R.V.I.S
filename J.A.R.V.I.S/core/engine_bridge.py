"""
core/engine_bridge.py — unified local bridge for 3D / game engines.

Targets
-------
- roblox   : HTTP long-poll queue (Studio plugin) + .rbxmx helpers
- blender  : headless CLI ops (mesh, decimate, export)
- godot    : project file injection (.tscn / .gd)

Protocol
--------
Structured JSON ops are enqueued or executed immediately:

    {"target": "roblox"|"blender"|"godot", "type": "...", ...}

Roblox ops reuse core.roblox_bridge (same port 28859 by default) so the
existing Studio Luau plugin keeps working.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

# Re-export / wrap the existing Roblox HTTP bridge
from core import roblox_bridge as _rbx

DEFAULT_PORT = 28859

_lock = threading.Lock()
_last_results: list[dict[str, Any]] = []


def status() -> dict[str, Any]:
    rbx = _rbx.status()
    return {
        "roblox_bridge": rbx,
        "blender": bool(_blender_bin()),
        "godot": bool(_godot_bin()),
        "last_results": list(_last_results[-10:]),
    }


def start_roblox_bridge(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> dict[str, Any]:
    return _rbx.start(host=host, port=port)


def stop_roblox_bridge() -> dict[str, Any]:
    return _rbx.stop()


def enqueue_roblox(op: dict[str, Any]) -> dict[str, Any]:
    """Queue an op for the Studio plugin (live)."""
    if not op.get("type"):
        raise ValueError("op.type required")
    if not _rbx.is_running():
        _rbx.start(port=int(op.get("port") or DEFAULT_PORT))
    rec = _rbx.enqueue(op)
    _remember({"target": "roblox", "mode": "live", "id": rec.get("id"), "op": op})
    return rec


# ── Binary discovery ─────────────────────────────────────────────────────────

def _blender_bin() -> Optional[str]:
    env = os.environ.get("BLENDER_PATH") or os.environ.get("BLENDER")
    if env and Path(env).is_file():
        return env
    w = shutil.which("blender")
    if w:
        return w
    if platform.system() == "Windows":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        hits = list(Path(pf).glob("Blender Foundation/Blender */blender.exe"))
        return str(hits[-1]) if hits else None
    if platform.system() == "Darwin":
        p = Path("/Applications/Blender.app/Contents/MacOS/Blender")
        return str(p) if p.is_file() else None
    for p in (Path("/usr/bin/blender"), Path("/snap/bin/blender")):
        if p.is_file():
            return str(p)
    return None


def _godot_bin() -> Optional[str]:
    env = os.environ.get("GODOT_PATH")
    if env and Path(env).is_file():
        return env
    for name in ("godot", "godot4"):
        w = shutil.which(name)
        if w:
            return w
    return None


def _remember(rec: dict[str, Any]) -> None:
    with _lock:
        _last_results.append({"ts": time.time(), **rec})
        if len(_last_results) > 100:
            del _last_results[:-100]


# ── Blender headless ─────────────────────────────────────────────────────────

def blender_run_script(script: str, *, timeout: int = 300) -> dict[str, Any]:
    bbin = _blender_bin()
    if not bbin:
        return {"ok": False, "error": "blender_not_found"}
    fd, tmp = tempfile.mkstemp(prefix="jarvis_engine_bpy_", suffix=".py")
    os.close(fd)
    Path(tmp).write_text(script, encoding="utf-8")
    try:
        proc = subprocess.run(
            [bbin, "--background", "--python", tmp],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        blob = (proc.stdout or "") + (proc.stderr or "")
        ok = proc.returncode == 0
        rec = {
            "ok": ok,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-4000:],
            "stderr": (proc.stderr or "")[-2000:],
            "log_tail": blob[-2000:],
        }
        _remember({"target": "blender", "mode": "headless", **rec})
        return rec
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        Path(tmp).unlink(missing_ok=True)


def blender_mesh_export(
    *,
    name: str = "Mesh",
    output: str,
    fmt: str = "fbx",
    prompt: str = "",
    decimate_ratio: float = 0.35,
) -> dict[str, Any]:
    out = str(Path(output).expanduser())
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower() if fmt else "fbx"
    lines = [
        "import bpy",
        "bpy.ops.wm.read_factory_settings(use_empty=True)",
        "bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1.5, location=(0,0,1.5))",
        "obj = bpy.context.active_object",
        "obj.name = %r" % name,
        "obj['jarvis_prompt'] = %r" % (prompt or ""),
        "try:",
        "    tex = bpy.data.textures.new('JarvisCloud', type='CLOUDS')",
        "    mod = obj.modifiers.new('Displace', 'DISPLACE')",
        "    mod.texture = tex",
        "    mod.strength = 0.35",
        "    bpy.ops.object.modifier_apply(modifier='Displace')",
        "except Exception as e:",
        "    print('displace skip', e)",
        "try:",
        "    d = obj.modifiers.new('Decimate', 'DECIMATE')",
        "    d.ratio = %s" % float(decimate_ratio),
        "    bpy.ops.object.modifier_apply(modifier='Decimate')",
        "except Exception as e:",
        "    print('decimate skip', e)",
        "out = %r" % out,
        "if out.lower().endswith('.obj'):",
        "    bpy.ops.wm.obj_export(filepath=out, export_selected_objects=False)",
        "else:",
        "    bpy.ops.export_scene.fbx(filepath=out, use_selection=False, apply_scale_options='FBX_SCALE_ALL')",
        "print('JARVIS_ENGINE_BRIDGE_OK', out)",
    ]
    result = blender_run_script("\n".join(lines) + "\n")
    result["output"] = out
    result["ok"] = result.get("ok") and "JARVIS_ENGINE_BRIDGE_OK" in (
        (result.get("stdout") or "") + (result.get("log_tail") or "")
    )
    return result


# ── Godot injection ──────────────────────────────────────────────────────────

def godot_ensure_project(root: str | Path, name: str = "JarvisGame") -> Path:
    root = Path(root).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    project = root / "project.godot"
    if not project.is_file():
        project.write_text(
            "; Generated by JARVIS engine_bridge\n"
            "config_version=5\n\n"
            "[application]\n\n"
            'config/name="%s"\n'
            'run/main_scene="res://main.tscn"\n'
            'config/features=PackedStringArray("4.2")\n' % name,
            encoding="utf-8",
        )
    main = root / "main.tscn"
    if not main.is_file():
        main.write_text(
            "[gd_scene format=3]\n\n[node name=\"Main\" type=\"Node2D\"]\n",
            encoding="utf-8",
        )
    return root


def godot_write_script(root: str | Path, rel_path: str, code: str) -> Path:
    root = Path(root).expanduser()
    dest = root / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(code, encoding="utf-8")
    _remember({"target": "godot", "mode": "write_script", "path": str(dest)})
    return dest


def godot_write_scene(root: str | Path, rel_path: str, content: str) -> Path:
    root = Path(root).expanduser()
    dest = root / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    _remember({"target": "godot", "mode": "write_scene", "path": str(dest)})
    return dest


# ── Unified dispatch ─────────────────────────────────────────────────────────

def dispatch(op: dict[str, Any]) -> dict[str, Any]:
    """
    Execute or enqueue a structured op.

    Examples
    --------
    {"target":"roblox","type":"build_structure","structure":"house"}
    {"target":"blender","type":"mesh_export","output":"/tmp/a.fbx","name":"Prop"}
    {"target":"godot","type":"write_script","root":"~/GodotProjects/X","rel":"player.gd","code":"..."}
    """
    target = str(op.get("target") or "roblox").lower()
    typ = str(op.get("type") or "").lower()

    if target == "roblox":
        if typ in ("mesh_export",):
            return {"ok": False, "error": "use target=blender for mesh_export"}
        return {"ok": True, "queued": enqueue_roblox(op)}

    if target == "blender":
        if typ in ("mesh_export", "export", "organic_mesh"):
            return blender_mesh_export(
                name=str(op.get("name") or "Mesh"),
                output=str(op.get("output") or op.get("path") or str(Path.home() / "jarvis_mesh.fbx")),
                fmt=str(op.get("format") or "fbx"),
                prompt=str(op.get("prompt") or ""),
                decimate_ratio=float(op.get("decimate_ratio") or 0.35),
            )
        if typ in ("script", "run_script"):
            return blender_run_script(str(op.get("script") or op.get("code") or ""))
        return {"ok": False, "error": "unknown_blender_type:%s" % typ}

    if target == "godot":
        root = op.get("root") or op.get("path")
        if not root:
            return {"ok": False, "error": "root required"}
        if typ in ("ensure_project", "new_project"):
            p = godot_ensure_project(root, str(op.get("name") or "JarvisGame"))
            return {"ok": True, "path": str(p)}
        if typ in ("write_script", "add_script"):
            p = godot_write_script(root, str(op.get("rel") or op.get("rel_path") or "script.gd"), str(op.get("code") or "extends Node\n"))
            return {"ok": True, "path": str(p)}
        if typ in ("write_scene", "add_scene"):
            p = godot_write_scene(root, str(op.get("rel") or "scene.tscn"), str(op.get("content") or "[gd_scene format=3]\n"))
            return {"ok": True, "path": str(p)}
        return {"ok": False, "error": "unknown_godot_type:%s" % typ}

    return {"ok": False, "error": "unknown_target:%s" % target}
