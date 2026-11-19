
"""Compila rotinas/gatilhos validando ActionRegistry e salvando configs."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.outcome import ask, done, failed

try:
    from core.action_hardening import atomic_write_json, project_root
except Exception:
    def project_root() -> Path:
        return Path(__file__).resolve().parents[3]
    def atomic_write_json(path, data, **kw):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

DESTRUCTIVE_HINTS = ("delete", "kill", "format", "shutdown", "rm ", "destructive", "limpar", "wipe")


def _routines_path() -> Path:
    return project_root() / "config" / "routines.json"


def _triggers_path() -> Path:
    return project_root() / "config" / "context_triggers.json"


def _known_actions() -> set[str]:
    names: set[str] = set()
    try:
        from core.action_loader import discover_actions
        reg = discover_actions(project_root() / "actions", logger=lambda *_: None)
        if hasattr(reg, "names"):
            names |= set(reg.names())
        elif hasattr(reg, "_actions"):
            names |= set(reg._actions.keys())
    except Exception:
        pass
    # filesystem fallback
    for p in (project_root() / "actions").rglob("*.py"):
        if p.name.startswith("_") or p.name == "__init__.py":
            continue
        names.add(p.stem)
    return names


def _parse_steps(description: str) -> list[dict[str, Any]]:
    """Heuristic: split by ' depois', 'entao', ';' or newlines into action-like steps."""
    parts = re.split(r"(?:\n+|;\s*|\bentao\b|\bdepois\b|\be depois\b)", description, flags=re.I)
    steps = []
    known = _known_actions()
    for part in parts:
        part = part.strip(" -•\t")
        if not part:
            continue
        # try first token as action name
        token = re.sub(r"[^a-z0-9_]", "", part.lower().split()[0] if part.split() else "")
        matched = token if token in known else None
        if not matched:
            for k in known:
                if k.replace("_", " ") in part.lower() or k in part.lower():
                    matched = k
                    break
        steps.append({"action": matched or "unknown", "raw": part[:200], "params": {}})
    return steps


def _validate_steps(steps: list[dict[str, Any]]) -> list[str]:
    known = _known_actions()
    errors = []
    for i, st in enumerate(steps):
        act = st.get("action") or "unknown"
        if act == "unknown" or act not in known:
            errors.append(f"passo {i+1}: action desconhecida '{act}' ({st.get('raw','')[:60]})")
        raw = (st.get("raw") or "").lower()
        if any(h in raw for h in DESTRUCTIVE_HINTS) or act in {"limpeza_profunda_disco", "process_manager"}:
            # require owner confirmation flag in routine metadata later
            st["requires_owner_gate"] = True
    return errors


def run(parameters=None, **_ctx) -> str:
    params = dict(parameters or {})
    action = str(params.get("action") or params.get("mode") or "listar").strip().lower()
    dry = str(params.get("dry_run") or "").lower() in ("1", "true", "sim", "yes")

    if action in ("listar", "list"):
        routines = {}
        triggers = {}
        try:
            if _routines_path().is_file():
                routines = json.loads(_routines_path().read_text(encoding="utf-8")).get("routines") or json.loads(_routines_path().read_text(encoding="utf-8"))
        except Exception:
            pass
        try:
            if _triggers_path().is_file():
                triggers = json.loads(_triggers_path().read_text(encoding="utf-8"))
        except Exception:
            pass
        return done("gerador_workflow_automacao", routines=list(routines) if isinstance(routines, dict) else routines, triggers_keys=list(triggers)[:20] if isinstance(triggers, dict) else [])

    if action in ("validar", "validate"):
        desc = str(params.get("descricao") or params.get("description") or "").strip()
        if not desc:
            return ask("gerador_workflow_automacao", "Informe descricao=")
        steps = _parse_steps(desc)
        errors = _validate_steps(steps)
        return done("gerador_workflow_automacao", action="validar", steps=steps, errors=errors, ok=not errors)

    if action in ("criar_rotina", "create_routine"):
        desc = str(params.get("descricao") or params.get("description") or "").strip()
        name = str(params.get("nome_rotina") or params.get("name") or "").strip()
        if not desc:
            return ask("gerador_workflow_automacao", "Descreva a rotina.")
        if not name:
            name = "rotina_" + re.sub(r"[^a-z0-9_]+", "_", desc.lower())[:24].strip("_")
        steps = _parse_steps(desc)
        errors = _validate_steps(steps)
        if errors and not dry:
            return failed("gerador_workflow_automacao", "validacao falhou", errors=errors, steps=steps)
        needs_gate = any(s.get("requires_owner_gate") for s in steps)
        routine = {"name": name, "description": desc, "steps": steps, "requires_owner_gate": needs_gate}
        if dry:
            return done("gerador_workflow_automacao", action="criar_rotina", dry_run=True, routine=routine, errors=errors)
        data: dict[str, Any] = {"routines": {}}
        if _routines_path().is_file():
            try:
                data = json.loads(_routines_path().read_text(encoding="utf-8", errors="replace"))
                if not isinstance(data, dict):
                    data = {"routines": {}}
                data.setdefault("routines", {})
            except Exception:
                data = {"routines": {}}
        if isinstance(data.get("routines"), dict):
            data["routines"][name] = routine
        else:
            data = {"routines": {name: routine}}
        atomic_write_json(_routines_path(), data)
        return done("gerador_workflow_automacao", action="criar_rotina", name=name, steps=len(steps), requires_owner_gate=needs_gate)

    if action in ("criar_gatilho", "create_trigger"):
        desc = str(params.get("descricao") or params.get("description") or "").strip()
        name = str(params.get("nome_rotina") or params.get("name") or "gatilho").strip()
        if not desc:
            return ask("gerador_workflow_automacao", "Descreva o gatilho.")
        steps = _parse_steps(desc)
        errors = _validate_steps(steps)
        trigger = {
            "name": name,
            "description": desc,
            "enabled": True,
            "steps": steps,
            "requires_owner_gate": any(s.get("requires_owner_gate") for s in steps),
        }
        if dry:
            return done("gerador_workflow_automacao", action="criar_gatilho", dry_run=True, trigger=trigger, errors=errors)
        if errors:
            return failed("gerador_workflow_automacao", "validacao falhou", errors=errors)
        data = {"triggers": []}
        if _triggers_path().is_file():
            try:
                data = json.loads(_triggers_path().read_text(encoding="utf-8", errors="replace"))
            except Exception:
                data = {"triggers": []}
        if isinstance(data, dict):
            if isinstance(data.get("triggers"), list):
                data["triggers"].append(trigger)
            else:
                data[name] = trigger
        atomic_write_json(_triggers_path(), data)
        return done("gerador_workflow_automacao", action="criar_gatilho", name=name)

    return failed("gerador_workflow_automacao", f"action desconhecida: {action}")
