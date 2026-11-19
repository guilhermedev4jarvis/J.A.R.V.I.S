"""Sessões de entrevista / debate / apresentação."""
from __future__ import annotations

import json
from pathlib import Path

from core.outcome import ask, done, failed

_ROOT = Path(__file__).resolve().parents[3]
_STATE = _ROOT / "memory" / "entrevista_sessions.json"


def _load() -> dict:
    if not _STATE.exists():
        return {"sessions": {}}
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"sessions": {}}


def _save(data: dict) -> None:
    _STATE.parent.mkdir(parents=True, exist_ok=True)
    _STATE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _llm(prompt: str) -> str:
    try:
        from core import llm_client
        for name in ("chat", "complete", "generate"):
            fn = getattr(llm_client, name, None)
            if not callable(fn):
                continue
            try:
                out = fn(prompt)
            except TypeError:
                out = fn(prompt=prompt)
            if isinstance(out, str) and out.strip():
                return out.strip()[:3000]
    except Exception:
        pass
    return ""


def run(parameters=None, **_ctx) -> str:
    params = dict(parameters or {})
    action = str(params.get("action") or params.get("mode") or "iniciar").strip().lower()
    session_id = str(params.get("session_id") or "default").strip()
    kind = str(params.get("kind") or params.get("tipo") or "entrevista").strip().lower()
    user_msg = str(params.get("message") or params.get("text") or params.get("query") or "").strip()
    data = _load()
    sessions = data.setdefault("sessions", {})

    if action in ("iniciar", "start", "nova"):
        sessions[session_id] = {"kind": kind, "turns": [], "active": True}
        opener = {
            "entrevista": "Fale sobre uma conquista recente relevante para a vaga.",
            "debate": "Defenda sua tese em 3 frases.",
            "apresentacao": "Apresente o tema em um minuto.",
        }.get(kind, "Sessão iniciada.")
        llm = _llm(f"Como {kind}, faça a pergunta inicial objetiva em português.") or opener
        sessions[session_id]["turns"].append({"role": "assistant", "text": llm})
        _save(data)
        return done("simulador_entrevista_debate", action="iniciar", session_id=session_id, kind=kind, prompt=llm)

    sess = sessions.get(session_id)
    if not sess or not sess.get("active"):
        return ask("simulador_entrevista_debate", "Nenhuma sessão ativa. Use action=iniciar.")

    if action in ("responder", "speak", "mensagem", "turn"):
        if not user_msg:
            return ask("simulador_entrevista_debate", "Envie message= com a sua resposta.")
        sess["turns"].append({"role": "user", "text": user_msg})
        history = "\n".join(f"{t['role']}: {t['text']}" for t in sess["turns"][-8:])
        reply = _llm(
            f"Você é um simulador de {sess.get('kind')}. Histórico:\n{history}\n"
            "Faça uma pergunta de follow-up objetiva em português."
        ) or f"Pode aprofundar: «{user_msg[:120]}»?"
        sess["turns"].append({"role": "assistant", "text": reply})
        _save(data)
        return done("simulador_entrevista_debate", action="responder", session_id=session_id, reply=reply)

    if action in ("finalizar", "avaliar", "end", "feedback"):
        history = "\n".join(f"{t['role']}: {t['text']}" for t in sess.get("turns") or [])
        feedback = _llm(
            "Avalie clareza, objetividade e domínio técnico. Histórico:\n" + history
        ) or "Sessão encerrada. Pratique respostas mais objetivas."
        sess["active"] = False
        sess["feedback"] = feedback
        _save(data)
        return done("simulador_entrevista_debate", action="finalizar", session_id=session_id, feedback=feedback)

    return failed("simulador_entrevista_debate", f"ação desconhecida: {action}")
