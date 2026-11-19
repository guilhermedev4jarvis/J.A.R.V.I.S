"""self_program — inspect/modify JARVIS modules via core.code_engine + sandbox."""
from __future__ import annotations

from pathlib import Path
from core.code_engine import get_engine
from core import sandbox as sandbox_mod
from core.static_safety import analyze_python
from core.outcome import done, failed, ask

_ROOT = Path(__file__).resolve().parents[2]


def self_program(parameters: dict | None = None, **_ctx) -> str:
    params = parameters or {}
    action = str(params.get("action") or "inspect").strip().lower()
    engine = get_engine()
    rel = str(params.get("path") or params.get("module") or "").strip()

    if action in ("status", "help"):
        return done("self_program", action="status", root=str(_ROOT), engine="core.code_engine")

    if action == "inspect":
        if not rel:
            return ask("self_program", "path relativo ao projeto?")
        path = (_ROOT / rel).resolve()
        if not str(path).startswith(str(_ROOT.resolve())):
            return failed("self_program", "path_outside_project")
        if not path.is_file():
            return failed("self_program", "not_found: %s" % path)
        vr = engine.analyze(path=str(path))
        return done(
            "self_program",
            action="inspect",
            path=str(path),
            syntax_ok=vr.ok,
            detail=vr.message,
            size=path.stat().st_size,
        )

    if action in ("propose", "improve"):
        if not rel:
            return ask("self_program", "path?")
        path = (_ROOT / rel).resolve()
        if not str(path).startswith(str(_ROOT.resolve())):
            return failed("self_program", "path_outside_project")
        goal = str(params.get("goal") or params.get("prompt") or "improve module").strip()
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            improved = engine.builder.build_one(goal, path=str(path), prior=source)
            vr = engine.verifier.verify_source(improved, filename=str(path))
            if not vr.ok:
                improved = engine.fix(improved, vr.message, path=str(path))
            # Never write directly into production without explicit write=true
            safety = analyze_python(improved, strict=True)
            if not safety.ok:
                return failed("self_program", "static_safety: %s" % safety.reason, action=action)
            write = str(params.get("write") or "false").lower() in ("1", "true", "yes")
            if write:
                ok, reason = sandbox_mod.path_is_allowed(str(path))
                if not ok:
                    return failed("self_program", "path_not_allowed: %s" % reason)
                try:
                    from core.owner_gate import OwnerGate
                    if not OwnerGate().verify_owner(
                        voice_path=params.get("owner_voice_path"),
                        camera=str(params.get("owner_camera") or "").lower() in ("1", "true", "yes"),
                    ):
                        return ask("self_program", "owner biometrics required to write into project")
                except Exception:
                    pass
                path.write_text(improved, encoding="utf-8")
                return done("self_program", action=action, path=str(path), written=True, chars=len(improved))
            out = _ROOT / "cache" / "self_program" / path.name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(improved, encoding="utf-8")
            return done("self_program", action=action, proposal=str(out), written=False, chars=len(improved))
        except Exception as e:
            return failed("self_program", str(e), action=action)

    return ask("self_program", "action?", hint="inspect|propose|status")


_LEGACY_TOOL = {
    "name": "self_program",
    "description": (
        "Inspeciona e propoe melhorias em modulos do proprio JARVIS via "
        "core.code_engine. Por padrao grava proposta em cache/ (write=true para aplicar). "
        "Acoes: inspect | propose | status."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING"},
            "path": {"type": "STRING"},
            "module": {"type": "STRING"},
            "goal": {"type": "STRING"},
            "prompt": {"type": "STRING"},
            "write": {"type": "STRING"},
        },
        "required": [],
    },
    "handler": self_program,
    "tier": "core",
    "risk": "destructive",
}
