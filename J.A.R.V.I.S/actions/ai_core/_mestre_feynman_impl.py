
"""mestre_feynman — aprendizado ativo por perguntas."""
from __future__ import annotations
from typing import Any
from core.outcome import done, ask
from actions.security._security_vision import speak_short

_sess: dict[str, Any] = {"active": False, "topic": "", "context": "", "history": []}

def _llm(sys: str, user: str) -> str:
    try:
        from core.llm_client import call_llm_text
        return (call_llm_text(user, system=sys, timeout=45) or "").strip()[:900]
    except Exception:
        return "Explique o conceito com suas palavras. O que você diria a um leigo?"

def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "start").lower()
    topic = str(p.get("topic") or p.get("query") or p.get("text") or "").strip()
    path = str(p.get("path") or "").strip()
    answer = str(p.get("text") or p.get("query") or "").strip() if action == "answer" else str(p.get("answer") or "")

    if action in ("end", "stop"):
        _sess.update({"active": False})
        speak_short("Sessão Feynman encerrada, Senhor.", player=player)
        return done("mestre_feynman", action="end")
    if action == "status":
        return done("mestre_feynman", active=_sess.get("active"), topic=_sess.get("topic"))

    if action == "start":
        ctx = ""
        if path:
            try:
                from .local_doc_rag import local_doc_rag
                ctx = str(local_doc_rag(parameters={"action": "read", "path": path, "query": topic or "resumo"}))[:3000]
            except Exception:
                ctx = ""
        if not topic and not ctx:
            return ask("mestre_feynman", "Sobre qual tema devo sabatiná-lo, Senhor?")
        _sess.update({"active": True, "topic": topic or path, "context": ctx, "history": []})
        q = _llm(
            "Você é um tutor Feynman rigoroso. Faça UMA pergunta desafiadora sobre o tema/contexto.",
            f"Tema: {topic}\nContexto: {ctx[:1500]}",
        )
        _sess["history"].append({"q": q})
        speak_short("Sabatina iniciada, Senhor.", player=player)
        return done("mestre_feynman", action="start", question=q, topic=_sess["topic"])

    if not _sess.get("active"):
        return ask("mestre_feynman", "Inicie uma sabatina primeiro, Senhor.")
    if not answer:
        answer = topic
    if not answer:
        return ask("mestre_feynman", "Sua explicação, Senhor?")
    prev_q = (_sess["history"][-1] or {}).get("q") if _sess["history"] else ""
    feedback = _llm(
        "Avalie a resposta do aluno: acertos, lacunas e próxima pergunta única. Português, tom elegante.",
        f"Pergunta: {prev_q}\nResposta: {answer}\nTema: {_sess.get('topic')}\nContexto: {_sess.get('context')[:800]}",
    )
    _sess["history"].append({"a": answer, "feedback": feedback})
    return done("mestre_feynman", action="answer", feedback=feedback)
