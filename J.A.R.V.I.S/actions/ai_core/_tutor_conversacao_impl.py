
"""tutor_conversacao — sessão interativa de idioma/entrevista."""
from __future__ import annotations
from typing import Any
from core.outcome import done, ask
from actions.security._security_vision import speak_short

_session: dict[str, Any] = {"active": False, "mode": None, "lang": "en", "history": []}

def _llm(system: str, user: str) -> str:
    try:
        from core.llm_client import call_llm_text
        r = call_llm_text(user, system=system, timeout=40)
        return (r or "").strip()[:800]
    except Exception:
        return "Continue, please. Focus on clear structure and vocabulary."

def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "start").lower()
    text = str(p.get("text") or p.get("query") or "").strip()
    mode = str(p.get("mode") or p.get("topic") or "english").lower()
    lang = str(p.get("language") or ("es" if "espan" in mode else "en"))

    if action in ("end", "encerrar", "stop"):
        hist = list(_session.get("history") or [])
        _session.update({"active": False, "history": []})
        fb = _llm(
            "Você é um tutor elegante. Dê feedback objetivo em português sobre vocabulário e clareza (4 frases).",
            "Diálogo:\n" + "\n".join(hist[-12:]),
        )
        speak_short("Treino encerrado, Senhor. Preparei o feedback.", player=player)
        return done("tutor_conversacao", action="end", feedback=fb)

    if action == "status":
        return done("tutor_conversacao", active=_session.get("active"), mode=_session.get("mode"), turns=len(_session.get("history") or []))

    if action in ("start", "treino", "simular"):
        if "entrev" in mode or "interview" in mode:
            _session.update({"active": True, "mode": "interview", "lang": "pt", "history": []})
            prompt = "Simule um recrutador exigente em português. Faça a primeira pergunta de entrevista."
        else:
            _session.update({"active": True, "mode": "language", "lang": lang, "history": []})
            prompt = f"You are a strict native tutor for language={lang}. Greet briefly and ask the first practice question in that language."
        reply = _llm(prompt, "Start session.")
        _session["history"].append("TUTOR: " + reply)
        speak_short("Sessão de treino iniciada, Senhor.", player=player)
        return done("tutor_conversacao", action="start", reply=reply, mode=_session["mode"])

    # turn
    if not _session.get("active"):
        return ask("tutor_conversacao", "Deseja iniciar treino de idioma ou entrevista, Senhor?")
    if not text:
        return ask("tutor_conversacao", "Sua resposta para o tutor, Senhor?")
    _session["history"].append("USER: " + text)
    sys = (
        "Continue the interview in Portuguese; one question at a time."
        if _session.get("mode") == "interview"
        else f"Continue language practice in {_session.get('lang')}; correct gently; ask next question."
    )
    reply = _llm(sys, text)
    _session["history"].append("TUTOR: " + reply)
    return done("tutor_conversacao", action="turn", reply=reply)
