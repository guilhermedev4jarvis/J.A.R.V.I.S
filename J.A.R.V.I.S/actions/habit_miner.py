"""Action: habit_miner - discover repetitive local screen routines."""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from core.outcome import ask, done, failed

_BASE = Path(__file__).resolve().parents[1]
_TIMELINE_PATH = _BASE / "memory" / "screen_memory_timeline.jsonl"
_ROUTINES_PATH = _BASE / "config" / "routines.json"
_lock = threading.Lock()


def _project_root() -> Path:
    return _BASE


def _timeline_paths(memory_dir: Optional[Path] = None) -> list[Path]:
    base = memory_dir or (_project_root() / "memory")
    paths: list[Path] = []
    for name in (
        "screen_memory_timeline.jsonl",
        "timeline.jsonl",
        "screen_timeline.jsonl",
        "events.jsonl",
        "episodes.jsonl",
    ):
        path = base / name
        if path.is_file():
            paths.append(path)
    timeline_dir = base / "timeline"
    if timeline_dir.is_dir():
        paths.extend(sorted(timeline_dir.glob("*.jsonl")))
    return paths


def _read_records(paths: Iterable[Path], limit: int = 2000) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    records.append(row)
                if len(records) >= limit:
                    break
        except Exception:
            continue
        if len(records) >= limit:
            break
    return records


def _timestamp(row: dict[str, Any]) -> Optional[datetime]:
    raw = next((row.get(k) for k in ("timestamp", "ts", "time", "datetime", "date", "at") if row.get(k)), None)
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw))
        except Exception:
            return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except Exception:
                pass
    return None


def _apps(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("app", "application", "process", "program", "window", "title"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    apps = row.get("apps")
    if isinstance(apps, list):
        values.extend(str(v).strip() for v in apps if str(v).strip())
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = re.sub(r"\s+", " ", value).strip()
        key = normalized.lower()
        if key not in seen:
            seen.add(key)
            unique.append(normalized)
    return unique[:8]


def analyze_patterns(parameters: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    p = dict(parameters or {})
    base_override = p.get("memory_dir")
    memory_dir = Path(str(base_override)).expanduser() if base_override else None
    limit = max(100, min(int(p.get("limit") or 2000), 10000))
    records = _read_records(_timeline_paths(memory_dir), limit=limit)
    hourly: dict[int, list[str]] = {}
    sequence_counts: dict[tuple[str, ...], int] = {}

    for row in records:
        apps = _apps(row)
        if not apps:
            continue
        stamp = _timestamp(row)
        if stamp is not None:
            bucket = hourly.setdefault(stamp.hour, [])
            for app in apps:
                if app not in bucket:
                    bucket.append(app)
        for pair in ((tuple(dict.fromkeys(apps[:2])) if len(apps) >= 2 else ()),):
            if len(pair) == 2:
                sequence_counts[pair] = sequence_counts.get(pair, 0) + 1

    patterns: list[dict[str, Any]] = []
    for apps, count in sorted(sequence_counts.items(), key=lambda item: (-item[1], item[0])):
        if count < 2:
            continue
        times = [hour for hour, names in hourly.items() if any(app.lower() in {n.lower() for n in names} for app in apps)]
        patterns.append({
            "apps": list(apps),
            "occurrences": count,
            "typical_hour": min(times) if times else None,
            "source": "timeline",
        })
    patterns.sort(key=lambda item: (-int(item["occurrences"]), item["apps"]))
    return patterns[:max(1, min(int(p.get("max_patterns") or 10), 50))]


def suggest_routines(patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for index, pattern in enumerate(patterns, 1):
        apps = [str(app) for app in pattern.get("apps") or []]
        if not apps:
            continue
        hour = pattern.get("typical_hour")
        if isinstance(hour, int):
            time_text = f" às {hour:02d}:00"
        else:
            time_text = ""
        name = re.sub(r"[^a-z0-9]+", "_", "_".join(apps).lower()).strip("_")[:60]
        suggestions.append({
            "name": name or f"rotina_habito_{index}",
            "apps": apps,
            "description": f"Rotina detectada para {', '.join(apps)}",
            "speech": f"Notei que voce costuma abrir {' e '.join(apps)} juntos{time_text}. Deseja salvar como rotina?",
            "occurrences": int(pattern.get("occurrences") or 1),
        })
    return suggestions


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return slug[:80] or "rotina_habito"


def _owner_confirmation(parameters: dict[str, Any]) -> tuple[bool, str]:
    approved = str(parameters.get("approved") or parameters.get("confirmed") or "").lower() in {
        "1", "true", "yes", "sim",
    }
    password = parameters.get("password")
    if not approved and not password:
        return False, "A rotina ainda nao foi aprovada pelo dono."
    if password:
        try:
            from core.owner_gate import require_owner

            auth = require_owner(
                tool_name="habit_miner",
                action="save_as_routine",
                password=str(password),
                text=str(parameters.get("text") or ""),
            )
            if isinstance(auth, dict) and not auth.get("ok"):
                return False, str(auth.get("detail") or "owner_gate denied")
        except Exception as exc:
            return False, f"owner_gate error: {exc}"
    return True, "confirmed"


def save_as_routine(parameters: dict[str, Any]) -> str:
    ok, detail = _owner_confirmation(parameters)
    if not ok:
        return ask("habit_miner", detail, action="save_as_routine")

    name = _slug(str(parameters.get("name") or parameters.get("routine") or ""))
    apps = parameters.get("apps")
    if isinstance(apps, str):
        apps = [v.strip() for v in apps.split(",") if v.strip()]
    if not isinstance(apps, list):
        apps = []
    apps = [str(app).strip() for app in apps if str(app).strip()]
    if not apps:
        return ask("habit_miner", "Informe os aplicativos da rotina.", action="save_as_routine")

    config_override = parameters.get("config_path")
    path = Path(str(config_override)).expanduser() if config_override else _ROUTINES_PATH
    try:
        from core.sandbox import path_is_allowed

        allowed, reason = path_is_allowed(str(path))
        if not allowed:
            return failed("habit_miner", f"path blocked by sandbox: {reason}", action="save_as_routine")
    except Exception:
        pass

    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {
            "version": 1,
            "routines": {},
        }
        if not isinstance(data, dict):
            data = {"version": 1, "routines": {}}
        routines = data.setdefault("routines", {})
        if not isinstance(routines, dict):
            routines = {}
            data["routines"] = routines

        existing = routines.get(name)
        if existing:
            return done(
                "habit_miner",
                action="save_as_routine",
                name=name,
                duplicate=True,
                saved=False,
            )

        steps = [
            {
                "tool": "open_app",
                "params": {"app_name": app},
                "speak": f"Abrindo {app}",
            }
            for app in apps
        ]
        routines[name] = {
            "description": str(parameters.get("description") or f"Rotina sugerida para {', '.join(apps)}"),
            "steps": steps,
            "requires_owner_gate": True,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return done(
            "habit_miner",
            action="save_as_routine",
            name=name,
            steps=len(steps),
            duplicate=False,
        )
    except Exception as exc:
        return failed("habit_miner", f"could not save routine: {exc}", action="save_as_routine")


def handler(
    parameters: Optional[dict[str, Any]] = None,
    player: Any = None,
    session_memory: Any = None,
    **ctx: Any,
) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "").strip().lower()
    try:
        if action == "analyze_patterns":
            patterns = analyze_patterns(p)
            return done(
                "habit_miner",
                action="analyze_patterns",
                count=len(patterns),
                patterns=json.dumps(patterns, ensure_ascii=False),
            )
        if action == "suggest_routines":
            patterns = analyze_patterns(p)
            suggestions = suggest_routines(patterns)
            return done(
                "habit_miner",
                action="suggest_routines",
                count=len(suggestions),
                suggestions=json.dumps(suggestions, ensure_ascii=False),
            )
        if action == "save_as_routine":
            return save_as_routine(p)
        return ask(
            "habit_miner",
            "Qual analise de habitos devo executar?",
            action=action or "missing",
            options="analyze_patterns|suggest_routines|save_as_routine",
        )
    except Exception as exc:
        return failed("habit_miner", f"habit analysis error: {exc}", action=action)


TOOL = {
    "name": "habit_miner",
    "description": (
        "Analyzes the local screen/timeline history, identifies recurring app and window "
        "sequences or hours, suggests voice-ready routines and saves approved routines "
        "to config/routines.json."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["analyze_patterns", "suggest_routines", "save_as_routine"],
            },
            "memory_dir": {"type": "STRING"},
            "config_path": {"type": "STRING"},
            "limit": {"type": "INTEGER"},
            "max_patterns": {"type": "INTEGER"},
            "name": {"type": "STRING"},
            "apps": {"type": "ARRAY", "items": {"type": "STRING"}},
            "description": {"type": "STRING"},
            "approved": {"type": "BOOLEAN"},
            "confirmed": {"type": "BOOLEAN"},
            "password": {"type": "STRING"},
        },
        "required": ["action"],
    },
    "handler": handler,
    "tier": "core",
    "risk": "autonomous",
}
