"""
core/code_engine.py — unified programming pipeline for MARK LXI / JARVIS.

Four stages
-----------
1. Architect       — multi-file change plan (LLM or heuristic)
2. Builder         — clean, typed source generation
3. SandboxVerifier — AST + py_compile (+ optional pytest) inside core.sandbox
4. AutoHealer      — up to N fix rounds via core.retry / LLM

Legacy actions (code_forge, code_helper, code_assist, code_review_local,
dev_agent, self_program) should call into this module so behaviour stays in
one place. Public entry points return the same outcome strings as core.outcome.
"""
from __future__ import annotations

import ast
import json
import py_compile
import re
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from core.outcome import done, failed, ask
from core.retry import retry_call
from core import sandbox as sandbox_mod

_BASE = Path(__file__).resolve().parents[1]
_CACHE = _BASE / "cache" / "code_engine"
_HISTORY = _BASE / "config" / "code_engine_history.json"
_MAX_FILE_CHARS = 120_000
_DEFAULT_HEAL_ROUNDS = 3

_SYSTEM_ARCHITECT = """You are a senior software architect.
Given a user goal, return ONLY a JSON object (no markdown) with shape:
{
  "summary": "one line",
  "files": [
    {"path": "relative/or/absolute.py", "action": "create|modify|delete", "intent": "why"}
  ],
  "tests": ["optional test commands or file names"],
  "risks": ["short risk notes"]
}
Prefer the smallest change set that satisfies the goal. Python 3.11+.
"""

_SYSTEM_BUILDER = """You are an expert Python 3.11+ engineer.
Output ONLY valid Python source code. No markdown fences, no prose.
Requirements:
- Complete, runnable when appropriate.
- Type hints where natural; docstrings on public functions.
- Explicit error handling for I/O and external calls.
- No broken TODOs.
- Prefer stdlib; if a third-party import is essential, top comment: # requires: package
"""

_SYSTEM_HEALER = """You are an expert Python debugger.
Given broken source and an error report, return ONLY the full corrected Python file.
No markdown fences, no explanations.
Keep the original intent and public API unless the bug forces a change.
Fix the root cause, not only the symptom.
"""


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class FilePlan:
    path: str
    action: str = "create"  # create | modify | delete
    intent: str = ""


@dataclass
class ArchitecturePlan:
    summary: str
    files: list[FilePlan] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "files": [asdict(f) for f in self.files],
            "tests": list(self.tests),
            "risks": list(self.risks),
        }


@dataclass
class VerifyResult:
    ok: bool
    stage: str
    message: str = ""
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


@dataclass
class PipelineResult:
    ok: bool
    stage: str
    plan: Optional[ArchitecturePlan] = None
    sources: dict[str, str] = field(default_factory=dict)
    verify: Optional[VerifyResult] = None
    healed_rounds: int = 0
    written: list[str] = field(default_factory=list)
    error: str = ""

    def as_outcome(self, tool_name: str = "code_engine") -> str:
        if self.ok:
            return done(
                tool_name,
                action=self.stage,
                summary=(self.plan.summary if self.plan else ""),
                files=list(self.sources.keys()) or self.written,
                written=self.written,
                healed_rounds=self.healed_rounds,
                verify_ok=True if self.verify is None else self.verify.ok,
            )
        return failed(
            tool_name,
            self.error or (self.verify.message if self.verify else "pipeline_failed"),
            stage=self.stage,
            healed_rounds=self.healed_rounds,
        )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _cache_dir() -> Path:
    _CACHE.mkdir(parents=True, exist_ok=True)
    return _CACHE


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```[a-zA-Z0-9_+-]*\r?\n?", "", text)
    text = re.sub(r"\r?\n?```\s*$", "", text)
    return text.strip()


def _append_hist(entry: dict[str, Any]) -> None:
    try:
        hist: list[Any] = []
        if _HISTORY.exists():
            hist = json.loads(_HISTORY.read_text(encoding="utf-8"))
            if not isinstance(hist, list):
                hist = []
        hist.append(entry)
        _HISTORY.parent.mkdir(parents=True, exist_ok=True)
        _HISTORY.write_text(
            json.dumps(hist[-80:], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _llm_text(prompt: str, system: str, timeout_ms: int = 90_000) -> str:
    """Best-effort LLM call through core.gemini / llm_client."""
    try:
        from core import gemini
        return (gemini.text(
            prompt,
            system=system,
            tier=getattr(gemini, "SMART", None) or "smart",
            timeout_ms=timeout_ms,
        ) or "").strip()
    except TypeError:
        # Older gemini.text signature
        try:
            from core import gemini
            return (gemini.text(prompt, tier=getattr(gemini, "SMART", "smart")) or "").strip()
        except Exception as e:
            raise RuntimeError("llm_unavailable: %s" % e) from e
    except Exception as e:
        # Fallback: llm_client
        try:
            from core import llm_client
            if hasattr(llm_client, "complete"):
                return (llm_client.complete(prompt, system=system) or "").strip()
            if hasattr(llm_client, "chat"):
                return (llm_client.chat(prompt) or "").strip()
        except Exception:
            pass
        raise RuntimeError("llm_unavailable: %s" % e) from e


def _safe_write(path: Path, content: str, *, dry_run: bool = False) -> None:
    path = path.expanduser()
    ok, reason = sandbox_mod.path_is_allowed(str(path))
    if not ok:
        raise PermissionError("path_not_allowed: %s (%s)" % (path, reason))
    if dry_run or sandbox_mod.is_dry_run():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── Stage 1: Architect ───────────────────────────────────────────────────────

class Architect:
    """Plan multi-file changes from a natural-language goal."""

    def plan(
        self,
        goal: str,
        *,
        context_files: Optional[dict[str, str]] = None,
        hint_paths: Optional[list[str]] = None,
    ) -> ArchitecturePlan:
        goal = (goal or "").strip()
        if not goal:
            return ArchitecturePlan(summary="empty goal", files=[])

        ctx_blob = ""
        if context_files:
            parts = []
            for p, src in list(context_files.items())[:12]:
                parts.append("### %s\n%s" % (p, src[:8000]))
            ctx_blob = "\n\n".join(parts)

        hints = ""
        if hint_paths:
            hints = "Preferred paths: " + ", ".join(hint_paths[:20])

        prompt = (
            "Goal:\n%s\n\n%s\n\n%s\n"
            % (goal, hints, ("Existing file excerpts:\n" + ctx_blob) if ctx_blob else "")
        )

        try:
            raw_text = _strip_fences(_llm_text(prompt, _SYSTEM_ARCHITECT))
            # extract JSON object
            m = re.search(r"\{[\s\S]*\}", raw_text)
            data = json.loads(m.group(0) if m else raw_text)
        except Exception:
            # Heuristic single-file plan
            safe = re.sub(r"[^\w\-]+", "_", goal.lower())[:40] or "module"
            path = str(_cache_dir() / ("%s_%s.py" % (safe, _stamp())))
            return ArchitecturePlan(
                summary="heuristic single-file plan",
                files=[FilePlan(path=path, action="create", intent=goal[:200])],
                tests=[],
                risks=["llm_plan_unavailable"],
            )

        files: list[FilePlan] = []
        for item in data.get("files") or []:
            if not isinstance(item, dict):
                continue
            p = str(item.get("path") or "").strip()
            if not p:
                continue
            files.append(FilePlan(
                path=p,
                action=str(item.get("action") or "create").lower(),
                intent=str(item.get("intent") or ""),
            ))
        if not files:
            safe = re.sub(r"[^\w\-]+", "_", goal.lower())[:40] or "module"
            files = [FilePlan(
                path=str(_cache_dir() / ("%s_%s.py" % (safe, _stamp()))),
                action="create",
                intent=goal[:200],
            )]
        return ArchitecturePlan(
            summary=str(data.get("summary") or goal[:120]),
            files=files,
            tests=[str(t) for t in (data.get("tests") or [])],
            risks=[str(r) for r in (data.get("risks") or [])],
            raw=data if isinstance(data, dict) else {},
        )


# ── Stage 2: Builder ─────────────────────────────────────────────────────────

class Builder:
    """Generate source for each file in the plan."""

    def build_one(self, intent: str, *, path: str = "", prior: str = "") -> str:
        prompt = "Target path: %s\n\nIntent:\n%s\n" % (path or "(new)", intent)
        if prior:
            prompt += "\nExisting source to improve:\n%s\n" % prior[:_MAX_FILE_CHARS]
        text = _strip_fences(_llm_text(prompt, _SYSTEM_BUILDER))
        if not text.strip():
            raise RuntimeError("builder_empty_response")
        return text

    def build_plan(
        self,
        plan: ArchitecturePlan,
        *,
        existing: Optional[dict[str, str]] = None,
    ) -> dict[str, str]:
        existing = existing or {}
        out: dict[str, str] = {}
        for fp in plan.files:
            if fp.action == "delete":
                continue
            prior = existing.get(fp.path, "")
            if not prior and Path(fp.path).is_file():
                try:
                    prior = Path(fp.path).read_text(encoding="utf-8", errors="replace")
                except Exception:
                    prior = ""
            intent = fp.intent or plan.summary
            out[fp.path] = self.build_one(intent, path=fp.path, prior=prior)
        return out


# ── Stage 3: SandboxVerifier ─────────────────────────────────────────────────

class SandboxVerifier:
    """Syntax + optional runtime checks under sandbox path policy."""

    def verify_source(self, source: str, *, filename: str = "<engine>") -> VerifyResult:
        if not source or not source.strip():
            return VerifyResult(False, "syntax", "empty_source")
        try:
            ast.parse(source, filename=filename)
        except SyntaxError as e:
            return VerifyResult(
                False, "syntax",
                "SyntaxError line %s: %s" % (e.lineno, e.msg),
                stderr=traceback.format_exc(),
            )
        # py_compile via temp file
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as tf:
                tf.write(source)
                tmp = tf.name
            try:
                py_compile.compile(tmp, doraise=True)
            finally:
                Path(tmp).unlink(missing_ok=True)
        except py_compile.PyCompileError as e:
            return VerifyResult(False, "py_compile", str(e), stderr=str(e))
        except Exception as e:
            return VerifyResult(False, "py_compile", str(e), stderr=traceback.format_exc())
        return VerifyResult(True, "syntax", "ok")

    def run_module(
        self,
        source: str,
        *,
        timeout: float = 15.0,
        args: Optional[list[str]] = None,
    ) -> VerifyResult:
        syn = self.verify_source(source)
        if not syn.ok:
            return syn
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(source)
            tmp = tf.name
        try:
            cmd = [sys.executable, tmp] + list(args or [])
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            if proc.returncode != 0:
                return VerifyResult(
                    False,
                    "run",
                    "exit_%s" % proc.returncode,
                    stdout=proc.stdout or "",
                    stderr=proc.stderr or "",
                    returncode=proc.returncode,
                )
            return VerifyResult(
                True, "run", "ok",
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                returncode=0,
            )
        except subprocess.TimeoutExpired:
            return VerifyResult(False, "run", "timeout")
        except Exception as e:
            return VerifyResult(False, "run", str(e), stderr=traceback.format_exc())
        finally:
            Path(tmp).unlink(missing_ok=True)

    def verify_sources(self, sources: dict[str, str]) -> VerifyResult:
        for path, src in sources.items():
            r = self.verify_source(src, filename=path)
            if not r.ok:
                r.message = "%s: %s" % (path, r.message)
                return r
        return VerifyResult(True, "syntax", "ok")


# ── Stage 4: AutoHealer ──────────────────────────────────────────────────────

class AutoHealer:
    """Fix failing sources up to max_rounds."""

    def __init__(self, max_rounds: int = _DEFAULT_HEAL_ROUNDS):
        self.max_rounds = max(1, int(max_rounds))
        self.verifier = SandboxVerifier()

    def heal_one(self, source: str, error_report: str, *, path: str = "") -> str:
        prompt = (
            "Path: %s\n\nError report:\n%s\n\nBroken source:\n%s\n"
            % (path or "(memory)", error_report[:8000], source[:_MAX_FILE_CHARS])
        )
        return _strip_fences(_llm_text(prompt, _SYSTEM_HEALER))

    def heal_sources(
        self,
        sources: dict[str, str],
        *,
        run: bool = False,
    ) -> tuple[dict[str, str], VerifyResult, int]:
        current = dict(sources)
        rounds = 0
        last = self.verifier.verify_sources(current)
        if last.ok and not run:
            return current, last, 0
        if last.ok and run:
            # run first file only for single-file forge flows
            if len(current) == 1:
                path, src = next(iter(current.items()))
                last = self.verifier.run_module(src)
                if last.ok:
                    return current, last, 0

        for rounds in range(1, self.max_rounds + 1):
            if last.ok:
                break
            # heal each failing path (or all if unknown)
            new_map: dict[str, str] = {}
            report = (last.message + "\n" + last.stderr + "\n" + last.stdout)[:8000]
            for path, src in current.items():
                try:
                    def _do() -> str:
                        return self.heal_one(src, report, path=path)
                    fixed = retry_call(_do, attempts=2, base_delay=0.4)
                except Exception:
                    fixed = self.heal_one(src, report, path=path)
                new_map[path] = fixed or src
            current = new_map
            last = self.verifier.verify_sources(current)
            if last.ok and run and len(current) == 1:
                path, src = next(iter(current.items()))
                last = self.verifier.run_module(src)
        return current, last, rounds


# ── Pipeline facade ──────────────────────────────────────────────────────────

class CodeEngine:
    """Orchestrates Architect → Builder → SandboxVerifier → AutoHealer."""

    def __init__(self, heal_rounds: int = _DEFAULT_HEAL_ROUNDS):
        self.architect = Architect()
        self.builder = Builder()
        self.verifier = SandboxVerifier()
        self.healer = AutoHealer(max_rounds=heal_rounds)

    def pipeline(
        self,
        goal: str,
        *,
        write: bool = True,
        run: bool = False,
        dry_run: bool = False,
        context_files: Optional[dict[str, str]] = None,
        heal_rounds: Optional[int] = None,
    ) -> PipelineResult:
        t0 = time.perf_counter()
        if heal_rounds is not None:
            self.healer = AutoHealer(max_rounds=heal_rounds)

        try:
            plan = self.architect.plan(goal, context_files=context_files)
        except Exception as e:
            return PipelineResult(False, "architect", error=str(e))

        try:
            sources = self.builder.build_plan(plan, existing=context_files)
        except Exception as e:
            return PipelineResult(False, "builder", plan=plan, error=str(e))

        sources, verify, rounds = self.healer.heal_sources(sources, run=run)
        if not verify.ok:
            _append_hist({
                "ts": _stamp(), "goal": goal[:200], "ok": False,
                "stage": verify.stage, "error": verify.message,
                "ms": int((time.perf_counter() - t0) * 1000),
            })
            return PipelineResult(
                False, verify.stage, plan=plan, sources=sources,
                verify=verify, healed_rounds=rounds, error=verify.message,
            )

        written: list[str] = []
        if write:
            for path, src in sources.items():
                try:
                    _safe_write(Path(path), src, dry_run=dry_run)
                    written.append(str(path))
                except Exception as e:
                    return PipelineResult(
                        False, "write", plan=plan, sources=sources,
                        verify=verify, healed_rounds=rounds,
                        written=written, error=str(e),
                    )

        _append_hist({
            "ts": _stamp(), "goal": goal[:200], "ok": True,
            "files": written or list(sources.keys()),
            "healed_rounds": rounds,
            "ms": int((time.perf_counter() - t0) * 1000),
        })
        return PipelineResult(
            True, "done", plan=plan, sources=sources,
            verify=verify, healed_rounds=rounds, written=written,
        )

    # ── Convenience API used by legacy wrappers ────────────────────────────

    def generate_python(self, prompt: str, *, dest: Optional[str] = None) -> PipelineResult:
        path = dest or str(_cache_dir() / ("gen_%s.py" % _stamp()))
        plan = ArchitecturePlan(
            summary=prompt[:120],
            files=[FilePlan(path=path, action="create", intent=prompt)],
        )
        try:
            src = self.builder.build_one(prompt, path=path)
        except Exception as e:
            return PipelineResult(False, "builder", plan=plan, error=str(e))
        sources, verify, rounds = self.healer.heal_sources({path: src}, run=False)
        if not verify.ok:
            return PipelineResult(
                False, verify.stage, plan=plan, sources=sources,
                verify=verify, healed_rounds=rounds, error=verify.message,
            )
        try:
            _safe_write(Path(path), sources[path])
        except Exception as e:
            return PipelineResult(
                False, "write", plan=plan, sources=sources,
                verify=verify, healed_rounds=rounds, error=str(e),
            )
        return PipelineResult(
            True, "generate", plan=plan, sources=sources,
            verify=verify, healed_rounds=rounds, written=[path],
        )

    def analyze(self, source: str = "", path: str = "") -> VerifyResult:
        if path and not source:
            source = Path(path).read_text(encoding="utf-8", errors="replace")
        return self.verifier.verify_source(source, filename=path or "<analyze>")

    def fix(self, source: str, error_report: str, *, path: str = "") -> str:
        return self.healer.heal_one(source, error_report, path=path)

    def forge(
        self,
        prompt: str,
        *,
        dest: Optional[str] = None,
        max_rounds: int = _DEFAULT_HEAL_ROUNDS,
        run: bool = True,
    ) -> PipelineResult:
        self.healer = AutoHealer(max_rounds=max_rounds)
        path = dest or str(_cache_dir() / ("forge_%s.py" % _stamp()))
        return self.pipeline(prompt, write=True, run=run, context_files={path: ""} if False else None)


# Module-level singleton for wrappers
_ENGINE: Optional[CodeEngine] = None


def get_engine(heal_rounds: int = _DEFAULT_HEAL_ROUNDS) -> CodeEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = CodeEngine(heal_rounds=heal_rounds)
    return _ENGINE
