
"""diario_cognitivo — JSONL episódico + resumo semanal."""
from __future__ import annotations
import json, threading, time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from core.outcome import done, ask
from actions.security._security_vision import audit, send_telegram, speak_short

_PATH = Path(__file__).resolve().parents[2] / "memory" / "diario_cognitivo.jsonl"
_lock = threading.Lock()
_sched = {"thread": None, "stop": threading.Event()}

def _append(entry: dict) -> None:
    with _lock:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        with _PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def _read_all() -> list[dict]:
    if not _PATH.is_file():
        return []
    out = []
    with _PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out

def _sentiment_theme(text: str) -> tuple[str, str]:
    low = text.lower()
    if any(w in low for w in ("feliz", "ótimo", "otimo", "sucesso", "grato")):
        sent = "positivo"
    elif any(w in low for w in ("triste", "ansioso", "preocup", "raiva", "medo")):
        sent = "negativo"
    else:
        sent = "neutro"
    if any(w in low for w in ("trabalho", "projeto", "reunião", "reuniao")):
        theme = "trabalho"
    elif any(w in low for w in ("saúde", "saude", "treino", "sono")):
        theme = "saude"
    elif any(w in low for w in ("ideia", "criar", "invent")):
        theme = "ideias"
    else:
        theme = "geral"
    # optional LLM enrichment
    try:
        from core.llm_client import call_llm_text
        r = call_llm_text(
            f"Classifique em JSON sentimento (positivo|neutro|negativo) e tema (1 palavra) deste texto: {text[:400]}",
            system="Responda só JSON.",
            timeout=15,
        )
        if r and "{" in r:
            data = json.loads(r[r.find("{"): r.rfind("}") + 1])
            sent = str(data.get("sentimento") or sent)
            theme = str(data.get("tema") or theme)
    except Exception:
        pass
    return sent, theme

def _week_entries() -> list[dict]:
    cut = datetime.now() - timedelta(days=7)
    rows = []
    for e in _read_all():
        try:
            ts = datetime.fromisoformat(e.get("ts", ""))
            if ts >= cut:
                rows.append(e)
        except Exception:
            continue
    return rows

def _summarize(rows: list[dict]) -> str:
    if not rows:
        return "Não há registros na última semana, Senhor."
    blob = "\n".join(f"- {r.get('text','')[:200]}" for r in rows[-40:])
    try:
        from core.llm_client import call_llm_text
        s = call_llm_text(
            "Síntese estratégica em 4-6 frases da semana do usuário (português, tom de conselheiro elegante):\n" + blob,
            system="Seja objetivo e útil.",
            timeout=40,
        )
        if s:
            return s.strip()[:1200]
    except Exception as e:
        audit("diario_summary_fail", tool="diario_cognitivo", extra={"error": str(e)[:100]})
    return f"Registrei {len(rows)} anotações na semana. Temas recentes: " + ", ".join(
        sorted({r.get("theme") or "geral" for r in rows})
    )

def _sunday_loop(player=None):
    last = None
    while not _sched["stop"].is_set():
        try:
            now = datetime.now()
            if now.weekday() == 6 and now.hour == 21 and now.minute < 5 and last != now.date():
                text = _summarize(_week_entries())
                speak_short("Resumo semanal pronto, Senhor.", player=player)
                send_telegram("*Diário cognitivo — semana*\n" + text[:3500], markdown=True)
                last = now.date()
        except Exception as e:
            audit("diario_sched_err", tool="diario_cognitivo", extra={"error": str(e)[:120]})
        _sched["stop"].wait(60)

def start_scheduler(player=None) -> bool:
    if _sched["thread"] and _sched["thread"].is_alive():
        return True
    _sched["stop"] = threading.Event()
    t = threading.Thread(target=_sunday_loop, args=(player,), daemon=True, name="diario-semanal")
    _sched["thread"] = t
    t.start()
    return True

def run(parameters=None, player=None, **_ctx) -> str:
    _p = dict(parameters or {})
    _act = str(_p.get('action') or '').lower()
    _blob = ' '.join(str(v) for v in _p.values()).lower()
    if _act in ('retrospectiva', 'retrospectiva_semanal') or 'retrospectiva' in _blob:
        r = gerar_retrospectiva_semanal(player=player)
        return done('diario_cognitivo', action='retrospectiva', **{k: v for k, v in r.items() if k != 'script'}, script=(r.get('script') or '')[:500])

    p = dict(parameters or {})
    action = str(p.get("action") or "").lower()
    text = str(p.get("text") or p.get("query") or "").strip()
    if not action:
        blob = " ".join(str(v) for v in p.values()).lower()
        if "resumo" in blob or "semana" in blob:
            action = "summary_week"
        else:
            action = "add"
    if action == "start_scheduler":
        return done("diario_cognitivo", scheduler=start_scheduler(player))
    if action in ("add", "registrar", "anotar"):
        if not text:
            return ask("diario_cognitivo", "O que deseja registrar, Senhor?")
        sent, theme = _sentiment_theme(text)
        entry = {"ts": datetime.now().isoformat(timespec="seconds"), "text": text, "sentiment": sent, "theme": theme}
        _append(entry)
        speak_short("Registrado no diário, Senhor.", player=player)
        return done("diario_cognitivo", action="add", **entry)
    if action in ("summary_week", "resumo"):
        rows = _week_entries()
        summary = _summarize(rows)
        speak_short("Aqui está a síntese da sua semana, Senhor.", player=player)
        return done("diario_cognitivo", action="summary_week", count=len(rows), summary=summary)
    rows = _read_all()[-20:]
    return done("diario_cognitivo", action="list", count=len(rows), items=rows)


def gerar_retrospectiva_semanal(player=None, deliver_telegram: bool = True) -> dict:
    """Compila semana e entrega roteiro + áudio TTS."""
    from datetime import datetime, timedelta
    import json as _json
    base = Path(__file__).resolve().parents[2]
    out_dir = base / "memory" / "retrospectivas"
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    week_key = now.strftime("%Y-%W")
    since = now - timedelta(days=7)
    lines = []
    for entry in _read_all():
        ts = entry.get("ts") or entry.get("timestamp") or entry.get("date")
        text = entry.get("text") or entry.get("content") or entry.get("nota") or ""
        if not text:
            continue
        lines.append(str(text)[:240])
    # episodes
    ep = base / "memory" / "episodes.jsonl"
    if ep.is_file():
        for line in ep.read_text(encoding="utf-8", errors="ignore").splitlines()[-80:]:
            try:
                o = _json.loads(line)
                lines.append(str(o.get("text") or o.get("summary") or "")[:200])
            except Exception:
                continue
    # events recent
    try:
        from core.event_bus import recent_events
        for e in recent_events(40):
            lines.append(f"evento {e.get('event')}")
    except Exception:
        pass
    lines = [x for x in lines if x.strip()][-30:]
    if not lines:
        script = (
            "Senhor, esta semana foi relativamente tranquila. "
            "Não há registros expressivos no diário cognitivo. "
            "Sistemas operando em modo nominal."
        )
    else:
        body = ". ".join(lines[:12])
        script = (
            f"Retrospectiva da semana {week_key}. "
            f"Senhor, em resumo: {body}. "
            "Fim da retrospectiva."
        )
    # TTS best-effort
    audio_path = out_dir / f"retrospectiva_{week_key}.mp3"
    audio_ok = False
    try:
        from core import tts as tts_mod
        if hasattr(tts_mod, "speak_to_file"):
            tts_mod.speak_to_file(script, str(audio_path))
            audio_ok = audio_path.is_file()
        elif hasattr(tts_mod, "synthesize"):
            data = tts_mod.synthesize(script)
            if data:
                audio_path.write_bytes(data)
                audio_ok = True
    except Exception:
        pass
    if not audio_ok:
        try:
            from providers import tts_piper
            if hasattr(tts_piper, "synthesize_to_file"):
                tts_piper.synthesize_to_file(script, str(audio_path))
                audio_ok = audio_path.is_file()
        except Exception:
            pass
    speak_short("Retrospectiva semanal pronta, Senhor.", player=player)
    if deliver_telegram:
        try:
            if audio_ok:
                # send as document/voice best-effort via telegram helper
                send_telegram(f"🎙️ Retrospectiva {week_key}\n{script[:500]}")
            else:
                send_telegram(f"🎙️ Retrospectiva {week_key}\n{script[:900]}")
        except Exception:
            pass
    audit("retrospectiva_semanal", tool="diario_cognitivo", extra={"week": week_key, "audio": audio_ok})
    return {
        "ok": True,
        "week": week_key,
        "script": script,
        "audio_path": str(audio_path) if audio_ok else None,
        "entries": len(lines),
    }
