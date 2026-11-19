
"""entretenimento_familia — trivia + curiosidades + placar."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from core.outcome import ask, done
from actions.security._security_vision import speak_short

_PATH = Path(__file__).resolve().parents[2] / "memory" / "placar_familia.json"
_lock = threading.Lock()
_sess: dict[str, Any] = {"active": False, "question": None, "answer": None, "score": {}}


def _load_score() -> dict:
    if not _PATH.is_file():
        return {"players": {}}
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"players": {}}


def _save_score(data: dict) -> None:
    with _lock:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _llm(prompt: str) -> str:
    try:
        from core.llm_client import call_llm_text
        return (call_llm_text(prompt, system="Português, tom carismático e familiar.", timeout=30) or "").strip()[:500]
    except Exception:
        return ""


def _parse_qa(raw: str) -> tuple[str, str]:
    question, answer = "Qual a capital do Brasil?", "Brasília"
    if not raw:
        return question, answer
    up = raw.replace("pergunta:", "PERGUNTA:").replace("resposta:", "RESPOSTA:")
    if "PERGUNTA:" in up and "RESPOSTA:" in up:
        question = up.split("PERGUNTA:", 1)[1].split("RESPOSTA:", 1)[0].strip(" \n|")
        answer = up.split("RESPOSTA:", 1)[1].strip(" \n|")
    return question or "Qual a capital do Brasil?", answer or "Brasília"


def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "").lower()
    text = str(p.get("text") or p.get("query") or "").strip()
    name = str(p.get("name") or "Família").strip() or "Família"

    if action in ("score", "placar"):
        data = _load_score()
        speak_short("Consultando o placar, Senhor.", player=player)
        return done("entretenimento_familia", action="score", placar=data.get("players") or {})

    if action in ("curiosity", "curiosidade"):
        cur = _llm("Conte uma curiosidade histórica breve e divertida em 2 frases.") or (
            "A Biblioteca de Alexandria chegou a reunir centenas de milhares de rolos de papiro."
        )
        speak_short(cur, player=player)
        return done("entretenimento_familia", action="curiosity", text=cur)

    if action in ("end", "encerrar"):
        _sess.update({"active": False, "question": None})
        speak_short("Quiz encerrado. Foi um prazer, família.", player=player)
        return done("entretenimento_familia", action="end", score=_sess.get("score"))

    if action in ("start_quiz", "start", "quiz"):
        q = _llm(
            "Crie UMA pergunta de conhecimentos gerais adequada para família brasileira. "
            "Formato: PERGUNTA: ... | RESPOSTA: ..."
        )
        question, answer = _parse_qa(q)
        _sess.update({"active": True, "question": question, "answer": answer})
        speak_short(f"Pergunta: {question}", player=player)
        return done("entretenimento_familia", action="start_quiz", question=question)

    if action == "answer" or (_sess.get("active") and text):
        if not _sess.get("active"):
            return ask("entretenimento_familia", "Inicie o quiz primeiro, Senhor.")
        user = text or str(p.get("text") or "")
        expected = str(_sess.get("answer") or "")
        ok = bool(user) and (
            user.lower() in expected.lower() or expected.lower() in user.lower()
        )
        if ok:
            _sess.setdefault("score", {})
            _sess["score"][name] = int(_sess["score"].get(name) or 0) + 1
            data = _load_score()
            data.setdefault("players", {})[name] = int(data["players"].get(name) or 0) + 1
            _save_score(data)
            speak_short("Resposta correta! Ponto para a família.", player=player)
            _sess["active"] = False
            return done("entretenimento_familia", action="answer", correct=True, score=_sess["score"])
        speak_short(f"Quase! A resposta era {expected}.", player=player)
        _sess["active"] = False
        return done("entretenimento_familia", action="answer", correct=False, expected=expected)

    return ask("entretenimento_familia", "Quiz, curiosidade ou placar, Senhor?")
