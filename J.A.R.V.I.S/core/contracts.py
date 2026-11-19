"""
core/contracts.py — formal tool contracts, risk tiers, and schema validation.

Goals
-----
1. Every discoverable TOOL/PLUGIN can declare a risk tier so the runtime can
   gate destructive work (confirm, dry-run, audit) without hard-coding names.
2. Schema helpers catch broken TOOL dicts early (already partly done in
   action_loader / plugin_loader; this module is the shared source of truth).
3. Golden-test helpers assert that a tool result string follows the outcome
   contract (status=done|unverified|failed|ask|started).

Risk tiers (TOOL["risk"] or PLUGIN["risk"])
------------------------------------------
    safe          read-only or easily reversible (search, list, clipboard read)
    review        mutates state but undoable or low-stakes (open app, volume)
    destructive   irreversible or high-stakes (delete, shutdown, send message,
                  write outside allowed roots) — needs confirm + audit
    autonomous    may run multi-step loops without per-step confirm
                  (desktop_agent, deep_research) — still respects agent_mode

Missing risk defaults to "review" so nothing new is silently treated as safe.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

# Outcome statuses the model and UI understand (see core/outcome.py).
OUTCOME_STATUSES = frozenset({"done", "unverified", "failed", "ask", "started"})

RISK_TIERS = frozenset({"safe", "review", "destructive", "autonomous"})

# Names that always require the human confirm gate regardless of declared risk.
ALWAYS_CONFIRM = frozenset({
    "shutdown", "restart", "power_off", "delete", "rm", "format",
    "send_message", "wipe", "factory_reset",
})

# Path-like parameter names that sandbox watches for write/delete.
PATH_PARAM_KEYS = frozenset({
    "path", "file_path", "filepath", "destination", "dest", "target",
    "folder", "directory", "src", "source", "output", "out",
})

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_STATUS_RE = re.compile(r"\bstatus=(done|unverified|failed|ask|started)\b", re.I)


@dataclass
class ContractIssue:
    level: str  # "error" | "warn"
    field: str
    message: str


@dataclass
class ToolContract:
    name: str
    description: str
    parameters: dict
    risk: str = "review"
    brief: str = ""
    requires_confirm: bool = False
    issues: list[ContractIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(i.level == "error" for i in self.issues)


def _as_dict(value: Any) -> Optional[dict]:
    return value if isinstance(value, dict) else None


def normalize_risk(value: Any) -> str:
    if isinstance(value, str):
        v = value.strip().lower()
        if v in RISK_TIERS:
            return v
    return "review"


def parse_tool_dict(tool: dict, *, kind: str = "TOOL") -> ToolContract:
    """Validate a module-level TOOL or PLUGIN dict. Never raises."""
    issues: list[ContractIssue] = []
    name = tool.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        issues.append(ContractIssue("error", "name", f"{kind}['name'] missing or invalid identifier."))
        name = str(name or "unknown")

    description = tool.get("description")
    if not isinstance(description, str) or not description.strip():
        issues.append(ContractIssue("error", "description", f"{kind}['description'] missing or empty."))
        description = description or ""

    parameters = tool.get("parameters", {"type": "OBJECT", "properties": {}})
    if not isinstance(parameters, dict) or parameters.get("type") != "OBJECT":
        issues.append(ContractIssue(
            "error", "parameters",
            f'{kind}["parameters"] must be a dict with "type": "OBJECT".',
        ))
        parameters = {"type": "OBJECT", "properties": {}}

    props = parameters.get("properties")
    if props is not None and not isinstance(props, dict):
        issues.append(ContractIssue("error", "parameters.properties", "properties must be a dict."))

    risk = normalize_risk(tool.get("risk"))
    brief = tool.get("brief") if isinstance(tool.get("brief"), str) else ""

    requires_confirm = bool(tool.get("requires_confirm"))
    if risk == "destructive":
        requires_confirm = True
    # Heuristic: action names that scream danger
    lowered = name.lower()
    if any(tok in lowered for tok in ("delete", "shutdown", "wipe", "format", "send_message")):
        requires_confirm = True
        if risk == "review":
            risk = "destructive"

    return ToolContract(
        name=name,
        description=description.strip(),
        parameters=parameters,
        risk=risk,
        brief=brief.strip(),
        requires_confirm=requires_confirm,
        issues=issues,
    )


def validate_outcome_string(result: str) -> list[str]:
    """Return a list of contract violations for a tool result string.

    Empty list means the string looks like a proper outcome line (or is empty).
    Plain prose without status= is a warn-level smell but not always wrong
    (some core tools still return free text); tests can choose strictness.
    """
    if result is None:
        return ["result is None"]
    text = str(result).strip()
    if not text:
        return ["empty result"]
    m = _STATUS_RE.search(text)
    if not m:
        return ["missing status=(done|unverified|failed|ask|started)"]
    return []


def assert_outcome(result: str, *, allowed: Iterable[str] = OUTCOME_STATUSES) -> str:
    """Return the status token or raise AssertionError (for unit tests)."""
    text = str(result or "")
    m = _STATUS_RE.search(text)
    if not m:
        raise AssertionError(f"No status= in result: {text[:200]!r}")
    status = m.group(1).lower()
    allowed_set = {a.lower() for a in allowed}
    if status not in allowed_set:
        raise AssertionError(f"status={status} not in {sorted(allowed_set)}")
    return status


def path_params_from_args(args: dict | None) -> dict[str, str]:
    """Extract path-like arguments for sandbox checks."""
    out: dict[str, str] = {}
    if not isinstance(args, dict):
        return out
    for k, v in args.items():
        if k.lower() in PATH_PARAM_KEYS and isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


def is_destructive_action(tool_name: str, args: dict | None, risk: str = "review") -> bool:
    """Heuristic used by sandbox + confirm gate."""
    if risk in ("destructive",):
        return True
    name = (tool_name or "").lower()
    if name in ALWAYS_CONFIRM or any(t in name for t in ALWAYS_CONFIRM):
        return True
    action = str((args or {}).get("action", "")).lower()
    if action in ALWAYS_CONFIRM or action in {
        "delete", "remove", "rm", "unlink", "shutdown", "restart",
        "write", "overwrite", "format", "wipe",
    }:
        return True
    return False


def risk_label_pt(risk: str) -> str:
    return {
        "safe": "seguro",
        "review": "revisão",
        "destructive": "destrutivo",
        "autonomous": "autônomo",
    }.get(normalize_risk(risk), risk)
