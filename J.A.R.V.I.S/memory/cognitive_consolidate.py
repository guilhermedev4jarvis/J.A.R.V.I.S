"""Cognitive consolidation: episodes/diario → long_term.json + graph.json."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_BASE = Path(__file__).resolve().parents[1]
_LONG = _BASE / "memory" / "long_term.json"
_GRAPH = _BASE / "memory" / "graph.json"
_EP = _BASE / "memory" / "episodes.jsonl"
_DIARIO = _BASE / "memory" / "diario_cognitivo.jsonl"

_WEEKDAYS = {
    "segunda": 0, "terça": 1, "terca": 1, "quarta": 2, "quinta": 3,
    "sexta": 4, "sábado": 5, "sabado": 5, "domingo": 6,
}


def _read_jsonl(path: Path, limit: int = 200) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            rows.append({"text": line})
    return rows


def _extract_commitments(text: str) -> list[dict]:
    low = text.lower()
    out = []
    # e.g. mãe tem consulta quinta às 14h
    m = re.search(
        r"(m[aã]e|pai|esposa|filho|filha|[\w]+)\s+tem\s+(consulta|reuni[aã]o|compromisso|medico|médico)[^\n]*?(segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo)?[^\n]*?(\d{1,2})\s*h?",
        low,
    )
    if m:
        wd = m.group(3)
        hour = int(m.group(4))
        target = None
        if wd:
            today = datetime.now()
            want = _WEEKDAYS.get(wd.replace("ç", "c").replace("á", "a"), today.weekday())
            delta = (want - today.weekday()) % 7
            target = (today + timedelta(days=delta)).date().isoformat()
        out.append(
            {
                "entity": m.group(1),
                "context": m.group(2),
                "target_date": target,
                "hour": hour,
                "status": "pending",
                "raw": text[:240],
            }
        )
    return out


def consolidate() -> dict[str, Any]:
    texts = []
    for row in _read_jsonl(_EP) + _read_jsonl(_DIARIO):
        texts.append(str(row.get("text") or row.get("content") or row.get("summary") or ""))
    commitments = []
    entities = set()
    for t in texts:
        if not t:
            continue
        commitments.extend(_extract_commitments(t))
        for ent in re.findall(r"\b(m[aã]e|pai|jarvis|port[aã]o|rio preto)\b", t.lower()):
            entities.add(ent)

    long_term = {"updated": datetime.now().isoformat(timespec="seconds"), "commitments": commitments[-50:], "notes": []}
    graph = {
        "updated": long_term["updated"],
        "nodes": [{"id": e, "type": "entity"} for e in sorted(entities)],
        "edges": [],
    }
    for c in commitments:
        graph["edges"].append(
            {
                "from": c.get("entity"),
                "to": c.get("context"),
                "target_date": c.get("target_date"),
                "status": c.get("status"),
            }
        )
    _LONG.parent.mkdir(parents=True, exist_ok=True)
    _LONG.write_text(json.dumps(long_term, ensure_ascii=False, indent=2), encoding="utf-8")
    _GRAPH.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"commitments": len(commitments), "entities": len(entities)}


def commitments_for_today() -> list[dict]:
    if not _LONG.is_file():
        return []
    try:
        data = json.loads(_LONG.read_text(encoding="utf-8"))
    except Exception:
        return []
    today = datetime.now().date().isoformat()
    tomorrow = (datetime.now() + timedelta(days=1)).date().isoformat()
    out = []
    for c in data.get("commitments") or []:
        td = c.get("target_date")
        if td in (today, tomorrow) and c.get("status") != "completed":
            out.append(c)
    return out
