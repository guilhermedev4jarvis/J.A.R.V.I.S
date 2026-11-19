"""Gera esqueleto de nova action com AST e static_safety."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from core.outcome import ask, done, failed

def _safety_scan(text: str):
    banned = ("os.system", "subprocess", "eval(", "exec(", "__import__", "rm -rf", "shutil.rmtree")
    low = text.lower()
    for b in banned:
        if b.lower() in low:
            return f"padrao bloqueado: {b}"
    try:
        from core import static_safety
        for name in ("check_text", "validate", "scan", "is_safe"):
            fn = getattr(static_safety, name, None)
            if not callable(fn):
                continue
            try:
                res = fn(text)
            except TypeError:
                continue
            if res is False:
                return "static_safety rejeitou"
            if isinstance(res, dict) and res.get("ok") is False:
                return str(res.get("reason") or "static_safety rejeitou")
    except Exception:
        pass
    return None

def _project_root() -> Path:
    here = Path(__file__).resolve().parent
    for p in [here, *here.parents]:
        if (p / "config").is_dir() and ((p / "core").is_dir() or (p / "main").exists()):
            return p
    return Path(__file__).resolve().parents[3]

_CATEGORIES = {
    "system", "desktop", "productivity", "ai_core", "security",
    "smarthome", "web_media", "finance_shopping", "misc",
}
_PUB = '"""Action pública gerada: {name}."""\nfrom __future__ import annotations\n\nfrom core.outcome import failed\nfrom ._{name}_impl import run as _run\n\n\ndef {name}(parameters=None, **ctx) -> str:\n    try:\n        return _run(parameters, **ctx)\n    except Exception as e:\n        return failed("{name}", str(e)[:240])\n\n\nTOOL = {{\n    "name": "{name}",\n    "description": {description!r},\n    "parameters": {{\n        "type": "OBJECT",\n        "properties": {{\n            "action": {{"type": "STRING"}},\n            "query": {{"type": "STRING"}},\n        }},\n        "required": [],\n    }},\n    "handler": {name},\n    "tier": "core",\n    "risk": "review",\n}}\n'
_IMPL = '"""Implementação gerada para {name}."""\nfrom __future__ import annotations\n\nfrom core.outcome import done\n\n\ndef run(parameters=None, **_ctx) -> str:\n    params = dict(parameters or {{}})\n    query = str(params.get("query") or params.get("action") or "").strip()\n    return done("{name}", message="Skill gerada. Implemente a lógica.", query=query)\n'


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s or s[0].isdigit():
        s = "skill_" + s
    return s[:48]


def run(parameters=None, **_ctx) -> str:
    params = dict(parameters or {})
    description = str(params.get("description") or params.get("query") or params.get("text") or "").strip()
    category = str(params.get("category") or "misc").strip().lower()
    name = str(params.get("name") or "").strip()
    if not name and description:
        name = _slug("_".join(description.split()[:4]))
    else:
        name = _slug(name or "nova_skill")
    if not description:
        return ask("criador_skill_por_voz", "Descreva a skill que devo criar.")
    _se = _safety_scan(description)
    if _se:
        return failed("criador_skill_por_voz", _se)
    if category not in _CATEGORIES:
        category = "misc"
    try:
        from core import static_safety
        check = getattr(static_safety, "check_text", None) or getattr(static_safety, "validate", None)
        if callable(check):
            try:
                check(description)
            except Exception as e:
                return failed("criador_skill_por_voz", f"bloqueado por static_safety: {e}")
    except Exception:
        pass
    pub = _PUB.format(name=name, description=description)
    impl = _IMPL.format(name=name)
    for label, src in ((name + ".py", pub), (f"_{name}_impl.py", impl)):
        try:
            ast.parse(src)
        except SyntaxError as e:
            return failed("criador_skill_por_voz", f"AST invalida em {label}: {e}")
        _se2 = _safety_scan(src)
        if _se2:
            return failed("criador_skill_por_voz", f"{label}: {_se2}")
        _se2 = _safety_scan(src)
        if _se2:
            return failed("criador_skill_por_voz", f"{label}: {_se2}")
    dest_dir = _project_root() / "actions" / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    pub_path = dest_dir / f"{name}.py"
    impl_path = dest_dir / f"_{name}_impl.py"
    if pub_path.exists() and not params.get("overwrite"):
        return failed("criador_skill_por_voz", f"já existe {pub_path.name}; passe overwrite=true")
    pub_path.write_text(pub, encoding="utf-8")
    impl_path.write_text(impl, encoding="utf-8")
    reload_msg = "hot_reload não acionado"
    try:
        from actions.system import hot_reload as hr
        fn = getattr(hr, "hot_reload", None) or getattr(hr, "run", None)
        if callable(fn):
            try:
                reload_msg = str(fn(parameters={"action": "actions"}))[:200]
            except TypeError:
                reload_msg = str(fn({"action": "actions"}))[:200]
    except Exception as e:
        reload_msg = f"reload skip: {e}"
    return done(
        "criador_skill_por_voz",
        name=name,
        category=category,
        public=str(pub_path.relative_to(_project_root())),
        impl=str(impl_path.relative_to(_project_root())),
        reload=reload_msg,
    )
