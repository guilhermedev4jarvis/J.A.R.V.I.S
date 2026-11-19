"""protocolo — 190 (silencioso, multi-canal) e demo (falado)."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from typing import Any, Callable, Optional

from core.outcome import ask, done, failed
from actions.security._security_vision import (
    analyze_vision,
    audit,
    connect_icsee_and_capture,
    redact,
    send_telegram,
    send_whatsapp,
    capture_with_fallbacks,
    sos_message,
    speak_short,
)

_SUPPORTED = frozenset({"190", "demo"})
_STEP_TIMEOUT = 8.0


def _normalize(name: str) -> str:
    n = (name or "").strip().lower().replace("protocolo", "").strip()
    n = "".join(n.split())
    if n in ("190", "emergencia", "emergência", "policia", "polícia"):
        return "190"
    if n in ("demo", "demonstracao", "demonstração"):
        return "demo"
    return n


def _step(name: str, fn: Callable[[], dict], timeout: float = _STEP_TIMEOUT) -> dict:
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            try:
                result = pool.submit(fn).result(timeout=timeout)
            except FutTimeout:
                audit("protocolo_step_timeout", tool="protocolo", extra={"step": name})
                return {"id": name, "ok": False, "reason": "timeout"}
        if isinstance(result, dict):
            result.setdefault("id", name)
            return result
        return {"id": name, "ok": True}
    except Exception as e:
        audit("protocolo_step_error", tool="protocolo", extra={"step": name, "error": str(e)[:160]})
        return {"id": name, "ok": False, "reason": redact(str(e))[:200]}



def _run_190(player=None) -> list[dict]:
    """Silent emergency: multi-strategy capture + parallel Telegram/WhatsApp."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    steps = []
    path = None
    png_ok = False
    try:
        cap = capture_with_fallbacks(player=None, load_delay=float(__import__("os").getenv("CAMERA_LOAD_DELAY_SEC") or 2.5))
        steps.append({"step": "capture", **{k: v for k, v in cap.items() if k != "png"}})
        path = cap.get("path")
        png_ok = bool(cap.get("ok"))
    except Exception as e:
        steps.append({"step": "capture", "ok": False, "error": str(e)[:160]})

    summary = "análise visual indisponível"
    try:
        if png_ok and path:
            from actions.security._security_vision import analyze_image_brief
            summary = str(analyze_image_brief(path) or summary)[:400]
    except Exception:
        try:
            from actions.security._security_vision import describe_capture
            summary = str(describe_capture(path) or summary)[:400]
        except Exception:
            pass

    addr = __import__("os").getenv("HOME_ADDRESS") or "Rua São Luiz, nº 244, Jardim Europa, São José do Rio Preto - SP"
    msg = (
        "🚨 EMERGÊNCIA! PEDIDO DE SOCORRO! Por favor, ligue imediatamente para a polícia (190) "
        f"e peça ajuda urgente no endereço: {addr}. "
        f"Situação detectada nas câmeras da casa (iCSee): {summary}"
    )

    results = {}
    def wa():
        results["whatsapp"] = send_whatsapp(msg, path, player=None)
    def tg():
        results["telegram"] = send_telegram(msg, path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(wa), pool.submit(tg)]
        for f in as_completed(futs, timeout=45):
            try:
                f.result()
            except Exception as e:
                results.setdefault("error", str(e)[:120])
    steps.append({"step": "alerts", **results})
    return steps



def _run_demo(player=None) -> list[dict]:
    steps = []
    speak_short("Iniciando demonstração, Senhor. Abro o iCSee e relato o que as câmeras mostram.", player=player)
    steps.append({"id": "announce", "ok": True})

    def diag():
        parts = []
        try:
            import actions.system.system_health as system_health
            parts.append(str(system_health.system_health(parameters={"action": "status"}))[:180])
        except Exception as e:
            audit("demo_health_fail", tool="protocolo", extra={"error": str(e)[:100]})
        try:
            import actions.system.network_status as network_status
            parts.append(str(network_status.network_status(parameters={"action": "status"}))[:180])
        except Exception as e:
            audit("demo_net_fail", tool="protocolo", extra={"error": str(e)[:100]})
        return {"ok": True, "parts": parts}

    steps.append(_step("diag", diag))
    speak_short("Diagnóstico concluído, Senhor.", player=player)

    c = _step("icsee", lambda: connect_icsee_and_capture(player=player), timeout=12)
    vision = ""
    if c.get("png"):
        vision = analyze_vision(c["png"])
        c["vision"] = vision
    c.pop("png", None)
    steps.append(c)
    if vision:
        speak_short(f"Nas câmeras, Senhor: {vision}", player=player)
    else:
        speak_short("Não obtive uma leitura clara das câmeras, Senhor.", player=player)
    speak_short("Demonstração encerrada. Nenhum alerta foi enviado.", player=player)
    steps.append({"id": "done", "ok": True})
    return steps


def run(parameters: Optional[dict] = None, player=None, session_memory=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "ativar").strip().lower()
    if action in ("list", "listar"):
        return done(
            "protocolo",
            op="list",
            protocolos=[
                {"nome": "190", "descricao": "Socorro silencioso multi-canal via iCSee"},
                {"nome": "demo", "descricao": "Demonstração falada sem emergência"},
            ],
        )
    name_raw = str(p.get("nome") or p.get("protocolo") or p.get("name") or "").strip()
    if not name_raw:
        return ask("protocolo", "Qual protocolo, Senhor: 190 ou demo?")
    key = _normalize(name_raw)
    if key not in _SUPPORTED:
        return failed("protocolo", "Apenas 190 e demo estão disponíveis, Senhor.")

    audit("protocolo_start", tool="protocolo", extra={"nome": key})
    try:
        steps = _run_190(player=player) if key == "190" else _run_demo(player=player)
    except Exception as e:
        audit("protocolo_crash", tool="protocolo", extra={"error": str(e)[:160]})
        if key == "190":
            return done("protocolo", op="ativar", nome="190", status="silent_partial", note="Protocolo 190 executado em silêncio.")
        return failed("protocolo", f"Falha na demonstração, Senhor: {redact(str(e))[:120]}")

    ok_n = sum(1 for s in steps if s.get("ok"))
    audit("protocolo_done", tool="protocolo", extra={"nome": key, "ok": ok_n})
    if key == "190":
        # Discrete status for LLM — no TTS was used
        return done(
            "protocolo",
            op="ativar",
            nome="190",
            steps_ok=ok_n,
            steps_total=len(steps),
            note="Protocolo 190 executado em silêncio.",
        )
    return done("protocolo", op="ativar", nome="demo", steps_ok=ok_n, steps_total=len(steps), steps=steps)
