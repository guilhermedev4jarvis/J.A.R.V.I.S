"""Consolida memória da semana em Markdown."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from core.outcome import done

def _project_root() -> Path:
    here = Path(__file__).resolve().parent
    for p in [here, *here.parents]:
        if (p / "config").is_dir() and ((p / "core").is_dir() or (p / "main").exists()):
            return p
    return Path(__file__).resolve().parents[3]



def _read_jsonl(path: Path, max_lines: int = 500) -> list:
    if not path.is_file():
        return []
    rows = []
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    rows.append({"raw": line[:200]})
    except OSError:
        return []
    return rows


def _read_csv_tail(path: Path, max_lines: int = 200) -> list[str]:
    if not path.is_file():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except OSError:
        return []


def run(parameters=None, **_ctx) -> str:
    params = dict(parameters or {})
    days = int(params.get("days") or 7)
    out_dir = _project_root() / "memory" / "retrospectivas"
    out_dir.mkdir(parents=True, exist_ok=True)
    diario = _read_jsonl(_project_root() / "memory" / "diario_cognitivo.jsonl")
    episodes = _read_jsonl(_project_root() / "memory" / "episodes.jsonl")
    gastos = _read_csv_tail(_project_root() / "memory" / "gastos.csv")
    now = datetime.now()
    out_path = out_dir / f"relatorio_semanal_{now.strftime('%Y%m%d_%H%M')}.md"
    md = [
        f"# Relatório semanal J.A.R.V.I.S. ({days} dias)",
        f"Gerado em: {now.isoformat(timespec='seconds')}",
        "",
        f"## Diário cognitivo ({len(diario)} registros)",
        f"## Episódios ({len(episodes)} registros)",
        f"## Gastos ({len(gastos)} linhas)",
        "",
        "## Amostra diário",
    ]
    for row in diario[-5:]:
        md.append(f"- {json.dumps(row, ensure_ascii=False)[:240]}")
    md += ["", "## Amostra episódios"]
    for row in episodes[-5:]:
        md.append(f"- {json.dumps(row, ensure_ascii=False)[:240]}")
    md += ["", "## Amostra gastos"]
    for row in gastos[-8:]:
        md.append(f"- {row[:240]}")
    out_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return done(
        "gerador_relatorio_semanal",
        path=str(out_path),
        diario=len(diario),
        episodes=len(episodes),
        gastos_lines=len(gastos),
        message=f"Relatório salvo em {out_path.name}",
    )
