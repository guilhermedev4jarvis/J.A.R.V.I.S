"""Shared security/vision helpers for protocolo, sentinel_patrol, telegram_commander.

Thread-safe iCSee capture, vision analysis, multi-channel alerts, evidence GC.
"""
from __future__ import annotations

UCF_CRIME_CLASSES = ['Abuse','Arrest','Arson','Assault','Burglary','Explosion','Fighting','Normal','RoadAccidents','Robbery','Shooting','Shoplifting','Stealing','Vandalism']
IMG_HEIGHT = 64
IMG_WIDTH = 64

import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

try:
    from core.resilience import http_request, sanitize_phone
except Exception:
    http_request = None
    def sanitize_phone(x):  # type: ignore
        return ''.join(c for c in str(x or '') if c.isdigit())

_BASE = Path(__file__).resolve().parents[2]
_EVID = _BASE / "memory" / "audit" / "evidencias"
_CAPTURE_LOCK = threading.Lock()
_FILE_LOCK = threading.Lock()

DEFAULT_ADDRESS = (
    "Rua São Luiz, nº 244, Jardim Europa, São José do Rio Preto - SP"
)
DEFAULT_ICSEE_WEB = "https://xmeye.net"
EVIDENCE_MAX_AGE_DAYS = 7


def env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default or "").strip()


def audit(kind: str, tool: str = "security_vision", extra: Optional[dict] = None) -> None:
    try:
        from core import audit as audit_mod
        safe = {}
        for k, v in (extra or {}).items():
            safe[k] = redact(str(v)) if isinstance(v, str) else v
        audit_mod.log_event(kind, tool=tool, extra=safe)
    except Exception as e:
        print(f"[{tool}] audit: {e}")


def redact(text: str) -> str:
    s = text or ""
    try:
        from core.redaction import redact_text
        s = redact_text(s)
    except Exception:
        pass
    s = re.sub(r"(rtsp://)([^:@/]+):([^@/]+)@", r"\1***:***@", s, flags=re.I)
    s = re.sub(r"(bot)\d+:[A-Za-z0-9_-]+", r"\1***:***", s, flags=re.I)
    s = re.sub(r"\b(\d{10,15})\b", lambda m: m.group(1)[:4] + "****" + m.group(1)[-2:], s)
    return s


def speak_short(text: str, player=None, *, silent: bool = False) -> None:
    """TTS: max ~2 short sentences, no emoji/markdown/URLs."""
    if silent or not (text or "").strip():
        return
    text = re.sub(r"[*_`#]+", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[🚨✅⚠️❌🎵]+", "", text).strip()
    # keep at most two sentences
    parts = re.split(r"(?<=[.!?])\s+", text)
    text = " ".join(parts[:2]).strip()
    if not text:
        return
    if player:
        for attr in ("plugin_say", "say", "request_say"):
            fn = getattr(player, attr, None)
            if callable(fn):
                try:
                    fn(text)
                    return
                except Exception as e:
                    audit("tts_player_fail", extra={"error": str(e)[:120]})
    try:
        from core import tts as tts_mod
        if hasattr(tts_mod, "speak"):
            tts_mod.speak(text)
    except Exception as e:
        audit("tts_fail", extra={"error": str(e)[:120]})


def evid_dir() -> Path:
    _EVID.mkdir(parents=True, exist_ok=True)
    return _EVID


def cleanup_old_evidence(max_age_days: int = EVIDENCE_MAX_AGE_DAYS) -> dict:
    """Delete evidence images older than max_age_days; keep *190* / emergencia markers."""
    root = evid_dir()
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    kept = 0
    with _FILE_LOCK:
        for path in root.iterdir():
            if not path.is_file():
                continue
            name = path.name.lower()
            # always keep emergency protocol artifacts
            if "190" in name or "emergenc" in name or name.endswith("_marker.json"):
                kept += 1
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    removed += 1
                else:
                    kept += 1
            except Exception as e:
                audit("evidence_gc_error", extra={"file": path.name, "error": str(e)[:100]})
    if removed:
        audit("evidence_gc", extra={"removed": removed, "kept": kept, "max_age_days": max_age_days})
    return {"removed": removed, "kept": kept}


def open_icsee(player=None) -> dict:
    """Open the desktop camera client (VMS.exe / iCSee) and focus it."""
    path = env("ICSEE_APP_PATH") or env("CAMERA_APP_PATH") or env("VMS_APP_PATH")
    name = env("ICSEE_APP_NAME") or env("CAMERA_APP_NAME") or env("VMS_APP_NAME") or env("VSM_APP_NAME") or "VSM.exe"
    web = env("ICSEE_WEB_URL") or env("CAMERA_APP_URL") or DEFAULT_ICSEE_WEB
    # Prefer VMS.exe (iCSee PC client). User may also have typed VSM.exe.
    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA", "")) if os.environ.get("LOCALAPPDATA") else None
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    extra_paths = [
        path,
        str(home / "Desktop" / "VMS.exe") if home else "",
        str(home / "Desktop" / "VSM.exe") if home else "",
        str(home / "Downloads" / "VMS.exe") if home else "",
        str(local / "VMS" / "VMS.exe") if local else "",
        str(local / "Programs" / "VMS" / "VMS.exe") if local else "",
        str(pf / "VMS" / "VMS.exe") if pf else "",
        str(pf86 / "VMS" / "VMS.exe") if pf86 else "",
        r"C:\VMS\VMS.exe",
        r"C:\Program Files\VMS\VMS.exe",
        r"C:\Program Files (x86)\VMS\VMS.exe",
    ]
    candidates = []
    for c in extra_paths:
        c = (c or "").strip()
        if c and c not in candidates:
            candidates.append(c)
    for c in (name, "VSM.exe", "VSM", "VMS.exe", "VMS", "iCSee", "iCSee.exe"):
        c = (c or "").strip()
        if c and c not in candidates:
            candidates.append(c)
    last = ""
    for app in candidates:
        app = (app or "").strip()
        if not app:
            continue
        try:
            import actions.desktop.open_app as open_app
            r = open_app.open_app(parameters={"app_name": app}, player=player)
            last = str(r)[:200]
            if "status=failed" not in last:
                try:
                    import actions.desktop.window_manager as window_manager
                    title = Path(app).stem if ("\\" in app or "/" in app) else app.replace(".exe", "")
                    window_manager.window_manager(parameters={"action": "focus", "title": title}, player=player)
                except Exception as e:
                    audit("icsee_focus_fail", extra={"error": str(e)[:120]})
                return {"ok": True, "mode": "desktop", "app": app}
        except Exception as e:
            last = str(e)[:200]
            audit("icsee_open_fail", extra={"app": app, "error": last})
    try:
        import actions.web_media.browser_control as browser_control
        r = browser_control.browser_control(parameters={"action": "open", "url": web}, player=player)
        return {"ok": "status=failed" not in str(r), "mode": "web", "url": redact(web)}
    except Exception as e:
        try:
            import webbrowser
            webbrowser.open(web)
            return {"ok": True, "mode": "web_webbrowser", "url": redact(web)}
        except Exception as e2:
            audit("icsee_web_fail", extra={"error": redact(f"{e};{e2}")[:160]})
            return {"ok": False, "reason": "icsee_unavailable"}


def capture_screen_png() -> dict:
    """Thread-safe screenshot → evidence folder."""
    with _CAPTURE_LOCK:
        cleanup_old_evidence()  # opportunistic GC
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = evid_dir() / f"{stamp}_icsee_screen.png"
        png = None
        try:
            from actions.desktop.screenshot_ocr import _capture_png  # type: ignore
            png = _capture_png()
        except Exception as e:
            audit("capture_helper_fail", extra={"error": str(e)[:120]})
        if png is None:
            try:
                import mss
                import mss.tools
                with mss.mss() as sct:
                    shot = sct.grab(sct.monitors[1])
                    png = mss.tools.to_png(shot.rgb, shot.size)
            except Exception as e:
                try:
                    from PIL import ImageGrab
                    import io
                    img = ImageGrab.grab()
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    png = buf.getvalue()
                except Exception as e2:
                    audit("capture_fail", extra={"error": f"{e};{e2}"[:160]})
                    return {"ok": False, "reason": "capture_failed"}
        if not png:
            return {"ok": False, "reason": "empty_frame"}
        try:
            path.write_bytes(png)
        except Exception as e:
            audit("capture_write_fail", extra={"error": str(e)[:120]})
            return {"ok": False, "reason": "write_failed"}
        return {
            "ok": True,
            "path": str(path),
            "file": str(path.relative_to(_BASE)),
            "png": png,
            "source": "screen",
        }


def capture_rtsp_optional() -> dict:
    url = env("ICSEE_RTSP_URL") or env("CAM_RTSP_1")
    if not url:
        return {"ok": False, "skipped": True}
    with _CAPTURE_LOCK:
        try:
            import cv2
            cap = cv2.VideoCapture(url)
            try:
                if not cap.isOpened():
                    return {"ok": False, "reason": "rtsp_open_failed"}
                frame = None
                t0 = time.time()
                while time.time() - t0 < 5.0:
                    ok, fr = cap.read()
                    if ok and fr is not None:
                        frame = fr
                        break
                    time.sleep(0.05)
                if frame is None:
                    return {"ok": False, "reason": "rtsp_no_frame"}
                path = evid_dir() / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_icsee_rtsp.jpg"
                cv2.imwrite(str(path), frame)
                ok2, buf = cv2.imencode(".png", frame)
                png = buf.tobytes() if ok2 else path.read_bytes()
                return {"ok": True, "path": str(path), "png": png, "source": "rtsp"}
            finally:
                cap.release()
        except Exception as e:
            audit("rtsp_fail", extra={"error": redact(str(e))[:160]})
            return {"ok": False, "reason": "rtsp_error"}


def connect_icsee_and_capture(player=None, load_delay: Optional[float] = None) -> dict:
    opened = open_icsee(player=player)
    delay = load_delay
    if delay is None:
        try:
            delay = float(env("CAMERA_LOAD_DELAY_SEC", "4") or "4")
        except Exception:
            delay = 4.0
    time.sleep(max(0.0, delay))
    rtsp = capture_rtsp_optional()
    screen = capture_screen_png()
    primary = screen if screen.get("ok") else rtsp
    out: dict[str, Any] = {
        "ok": bool(primary.get("ok")),
        "icsee_open": opened,
        "source": primary.get("source"),
        "path": primary.get("path"),
        "file": primary.get("file"),
        "png": primary.get("png"),
    }
    if not out["ok"]:
        out["reason"] = primary.get("reason") or "no_image"
    return out


def analyze_vision(png: bytes, context: str = "câmeras iCSee") -> str:
    prompt = (
        f"Analise esta imagem de {context}. Em português, no máximo 2 frases objetivas: "
        "pessoas, veículos, movimento suspeito. Se só aparecer a interface do app, diga."
    )
    try:
        from core import gemini as gem
        from google.genai import types as gtypes
        key = gem.api_key() if hasattr(gem, "api_key") else ""
        if key:
            part = gtypes.Part.from_bytes(data=png, mime_type="image/png")
            reply = gem.text([prompt, part], timeout_ms=25_000, key=key)
            if reply:
                return reply.strip()[:500]
    except Exception as e:
        audit("vision_gemini_fail", extra={"error": str(e)[:140]})
    try:
        from core.llm_client import call_llm_text
        reply = call_llm_text(prompt, system="Descrição visual breve em português.", timeout=20)
        if reply:
            return reply.strip()[:500]
    except Exception as e:
        audit("vision_llm_fail", extra={"error": str(e)[:140]})
    return "Sem descrição visual disponível no momento."


def send_telegram(msg: str, image_path: Optional[str] = None, *, markdown: bool = False) -> dict:
    """Deliver text/photo via Telegram with timeout + retry."""
    token = env("TELEGRAM_BOT_TOKEN")
    chat = env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return {"ok": False, "reason": "telegram_not_configured"}
    base = f"https://api.telegram.org/bot{token}"
    try:
        import requests
        if image_path and Path(image_path).is_file():
            data = {"chat_id": chat, "caption": (msg or "")[:1024]}
            if markdown:
                data["parse_mode"] = "Markdown"
            def _photo():
                with open(image_path, "rb") as fh:
                    if http_request:
                        return http_request("POST", f"{base}/sendPhoto", data=data, files={"photo": fh}, timeout=(4, 20), attempts=3)
                    return requests.post(f"{base}/sendPhoto", data=data, files={"photo": fh}, timeout=(4, 20))
            r = _photo()
            if getattr(r, "status_code", 0) == 200:
                return {"ok": True, "channel": "telegram", "photo": True}
        payload = {"chat_id": chat, "text": (msg or "")[:4000]}
        if markdown:
            payload["parse_mode"] = "Markdown"
        def _msg():
            if http_request:
                return http_request("POST", f"{base}/sendMessage", json=payload, timeout=(4, 12), attempts=3)
            return requests.post(f"{base}/sendMessage", json=payload, timeout=(4, 12))
        r = _msg()
        ok = getattr(r, "status_code", 0) == 200
        return {"ok": ok, "channel": "telegram", "photo": False}
    except Exception as e:
        audit("telegram_send_fail", extra={"error": str(e)[:160]})
        return {"ok": False, "reason": f"offline_or_error:{e.__class__.__name__}"}


def send_whatsapp(msg: str, image_path: Optional[str] = None, player=None) -> dict:
    phone = re.sub(r"[^\d]", "", env("EMERGENCY_CONTACT_PHONE", "5517999999999"))
    name = env("EMERGENCY_CONTACT_NAME") or env("EMERGENCY_CONTACT") or ""
    contact = name or phone
    if not contact:
        return {"ok": False, "channel": "whatsapp", "reason": "no_contact"}
    params: dict[str, Any] = {"message": msg, "contact": contact}
    if phone:
        params["phone"] = phone
    if image_path:
        params["image"] = image_path
        params["file"] = image_path
    try:
        import actions.web_media.whatsapp_web as whatsapp_web
        r = whatsapp_web.whatsapp_web(parameters=params, player=player)
        return {"ok": "status=failed" not in str(r), "channel": "whatsapp_web"}
    except Exception as e:
        try:
            import actions.web_media.send_message as send_message
            sp = {"channel": "whatsapp", "to": contact, "message": msg}
            if image_path:
                sp["file"] = image_path
            r = send_message.send_message(parameters=sp, player=player)
            return {"ok": "status=failed" not in str(r), "channel": "send_message"}
        except Exception as e2:
            audit("whatsapp_fail", extra={"error": f"{e};{e2}"[:160]})
            return {"ok": False, "channel": "whatsapp", "reason": str(e2)[:160]}


def home_address() -> str:
    return env("HOME_ADDRESS") or env("ENDERECO_RESIDENCIA") or DEFAULT_ADDRESS


def sos_message(vision: str) -> str:
    vis = (vision or "sem descrição visual").strip()[:400]
    return (
        "🚨 EMERGÊNCIA! PEDIDO DE SOCORRO! Por favor, ligue imediatamente para a "
        f"polícia (190) e peça ajuda urgente no endereço: {home_address()}. "
        f"Situação detectada nas câmeras da casa (iCSee): {vis}"
    )


def capture_sequence(count: int = 5, interval_sec: float = 2.5, player=None) -> dict:
    """Capture `count` iCSee/screen frames spaced by interval_sec (thread-safe)."""
    # legacy path kept; prefer capture_with_fallbacks callers
    open_icsee(player=player)
    time.sleep(1.0)
    frames = []
    for i in range(count):
        shot = capture_screen_png()
        # rename with sequence index
        if shot.get("ok") and shot.get("path"):
            src = Path(shot["path"])
            dest = evid_dir() / f"{src.stem}_seq{i+1}{src.suffix}"
            try:
                if src.exists():
                    src.replace(dest)
                    shot["path"] = str(dest)
                    shot["file"] = str(dest.relative_to(_BASE))
            except Exception:
                dest = src
            frames.append({k: v for k, v in shot.items() if k != "png"})
            # keep png only in memory list separately
            frames[-1]["_png"] = shot.get("png")
        else:
            frames.append({"ok": False, "index": i + 1, "reason": shot.get("reason")})
        if i < count - 1:
            time.sleep(max(0.1, interval_sec))
    ok_n = sum(1 for f in frames if f.get("ok"))
    return {"ok": ok_n > 0, "frames": frames, "count": ok_n}


def _load_image_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except Exception:
        return None


def frames_from_folder(folder: Path, count: int = 5) -> list:
    """Pick `count` equally spaced image frames from folder (recursive)."""
    exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
    files = sorted([p for p in folder.rglob("*") if p.suffix.lower() in exts and p.is_file()])
    if not files:
        return []
    if len(files) <= count:
        chosen = files
    else:
        # equally spaced indices from start to end
        idxs = [round(i * (len(files) - 1) / (count - 1)) for i in range(count)]
        chosen = [files[i] for i in idxs]
    frames = []
    for i, fp in enumerate(chosen):
        data = _load_image_bytes(fp)
        frames.append({
            "ok": bool(data),
            "path": str(fp),
            "file": str(fp),
            "index": i + 1,
            "_png": data,
            "source": "disk",
        })
    return frames


def analyze_perimeter_sequence(frames: list, *, request_context: str = "", camera_profile: str = "mixed") -> dict:
    """Multimodal temporal analysis with residential camera context.

    camera_profile:
      - interior: any unknown person => AMEACA_CRITICA (family folder memory/familia/)
      - gate: sidewalk pass vs intrusion attempt
      - mixed: default heuristic
    """
    import json as _json
    pngs = [f.get("_png") for f in frames if f.get("ok") and f.get("_png")]
    family_note = ""
    fam = _BASE / "memory" / "familia"
    if fam.is_dir():
        family_note = f" Pessoas cadastradas em familia/: {len(list(fam.glob('*')))} arquivos de referência."
    cam_rules = {
        "interior": (
            "Câmera 1 — INTERIOR da casa: qualquer pessoa NÃO claramente reconhecida como morador "
            "cadastrado deve ser AMEACA_CRITICA imediata."
        ),
        "gate": (
            "Câmera 2 — PORTÃO secundário: diferencie pedestre/carro na calçada (NORMAL/ATENCAO) "
            "de tentativa de invasão (parado no portão, saltando muro, agachado, rosto coberto = AMEACA_CRITICA)."
        ),
        "mixed": (
            "Contexto misto interior/portão. Interior: desconhecido = crítico. "
            "Portão: passagem vs invasão."
        ),
    }
    prompt = (
        "Você é analista de segurança residencial. Analise estas "
        f"{len(pngs)} imagens EM ORDEM CRONOLÓGICA. "
        f"{cam_rules.get(camera_profile, cam_rules['mixed'])}{family_note} "
        "Use também anomalia_ucf em ['Abuse', 'Arrest', 'Arson', 'Assault', 'Burglary', 'Explosion', 'Fighting', 'Normal', 'RoadAccidents', 'Robbery', 'Shooting', 'Shoplifting', 'Stealing', 'Vandalism'] quando aplicável. Responda SOMENTE JSON válido com: classificacao (NORMAL|ATENCAO|AMEACA_CRITICA), anomalia_ucf, "
        "nivel_risco (0-10), evolucao_movimento (string), descricao_tatica (string pt-BR 2-4 frases), "
        "camera_inferida (interior|portao|indefinido)."
    )
    if request_context:
        prompt += f" Contexto extra: {request_context}"
    raw = ""
    try:
        from core import gemini as gem
        from google.genai import types as gtypes
        key = gem.api_key() if hasattr(gem, "api_key") else ""
        if key and pngs:
            parts = [prompt]
            for b in pngs[:5]:
                mime = "image/jpeg" if (b[:3] == b"\xff\xd8\xff") else "image/png"
                parts.append(gtypes.Part.from_bytes(data=b, mime_type=mime))
            raw = gem.text(parts, timeout_ms=60_000, key=key) or ""
    except Exception as e:
        audit("perimeter_gemini_fail", extra={"error": str(e)[:140]})
    if not raw:
        try:
            from core.llm_client import call_llm_text
            raw = call_llm_text(prompt + f" ({len(pngs)} frames)", system="Responda só JSON.", timeout=40) or ""
        except Exception as e:
            audit("perimeter_llm_fail", extra={"error": str(e)[:140]})
    data = {
        "classificacao": "NORMAL",
        "nivel_risco": 0,
        "evolucao_movimento": "sem análise multimodal disponível",
        "descricao_tatica": "Varredura concluída sem veredito de modelo.",
        "camera_inferida": "indefinido",
    }
    if raw:
        try:
            start, end = raw.find("{"), raw.rfind("}")
            if start >= 0 and end > start:
                parsed = _json.loads(raw[start : end + 1])
                if isinstance(parsed, dict):
                    data.update({k: parsed.get(k, data.get(k)) for k in data})
        except Exception:
            data["descricao_tatica"] = raw[:400]
    light = [{k: v for k, v in f.items() if k != "_png"} for f in frames]
    return {"ok": True, "analysis": data, "frames": light}


def simulate_invasion_scan(player=None, *, folder: str | None = None) -> dict:
    """Use memory/teste_cameras (Burglary) frames for temporal threat simulation."""
    root = Path(folder) if folder else (_BASE / "memory" / "teste_cameras")
    if not root.is_dir():
        return {"ok": False, "reason": "teste_cameras_missing", "path": str(root)}
    speak_short("Simulando análise de invasor com a amostra local, Senhor.", player=player)
    frames = frames_from_folder(root, count=5)
    if not frames:
        return {"ok": False, "reason": "no_frames", "path": str(root)}
    result = analyze_perimeter_sequence(
        frames,
        request_context="Simulação UCF-Crime / Burglary — trate como possível arrombamento.",
        camera_profile="gate",
    )
    analysis = result.get("analysis") or {}
    cls = str(analysis.get("classificacao") or "NORMAL").upper()
    desc = str(analysis.get("descricao_tatica") or "")
    if cls == "AMEACA_CRITICA":
        speak_short("Simulação: ameaça crítica detectada, Senhor.", player=player)
    elif cls == "ATENCAO":
        speak_short("Simulação: movimento que merece atenção, Senhor.", player=player)
    else:
        speak_short("Simulação concluída, Senhor.", player=player)
    paths = [f.get("path") for f in (result.get("frames") or []) if f.get("path")]
    msg = (
        "*Simulação de invasão (Kaggle/UCF)*" + chr(10)
        + f"Classificação: *{cls}* · Risco: *{analysis.get('nivel_risco')}*" + chr(10)
        + f"{analysis.get('evolucao_movimento')}" + chr(10)
        + desc
    )
    if paths:
        send_telegram(msg, paths[0], markdown=True)
        for extra in paths[1:4]:
            send_telegram(f"Frame simulação — {cls}", extra, markdown=True)
    else:
        send_telegram(msg, markdown=True)
    audit("simulate_invasion", extra={"classificacao": cls, "frames": len(paths)})
    return {"ok": True, "analysis": analysis, "frame_paths": paths, "count": len(paths), "source": str(root)}


def run_perimeter_scan(player=None, *, announce: bool = True, camera_profile: str = "mixed") -> dict:
    """iCSee: announce → 5 frames @ 2.5s → temporal analysis with camera rules."""
    if announce:
        speak_short(
            "Iniciando varredura sequencial do perímetro, Senhor. Aguarde dez segundos.",
            player=player,
        )
    seq = capture_sequence(5, 2.5, player=player)
    result = analyze_perimeter_sequence(seq.get("frames") or [], camera_profile=camera_profile)
    analysis = result.get("analysis") or {}
    cls = str(analysis.get("classificacao") or "NORMAL").upper()
    desc = str(analysis.get("descricao_tatica") or "")
    if cls == "AMEACA_CRITICA":
        speak_short("Atenção, Senhor. Ameaça crítica no perímetro.", player=player)
    elif cls == "ATENCAO":
        speak_short("Senhor, há movimento que merece atenção no perímetro.", player=player)
    else:
        speak_short("Perímetro aparentemente normal, Senhor.", player=player)
    paths = [f.get("path") for f in (result.get("frames") or []) if f.get("path")]
    msg = (
        "*Varredura de perímetro*" + chr(10)
        + f"Classificação: *{cls}* · Risco: *{analysis.get('nivel_risco')}*" + chr(10)
        + f"{analysis.get('evolucao_movimento')}" + chr(10)
        + desc
    )
    if paths:
        send_telegram(msg, paths[0], markdown=True)
        for extra_path in paths[1:4]:
            send_telegram(f"Frame sequência — {cls}", extra_path, markdown=True)
    else:
        send_telegram(msg, markdown=True)
    audit("perimeter_scan", extra={"classificacao": cls, "frames": len(paths)})
    return {"ok": True, "analysis": analysis, "frame_paths": paths, "count": len(paths)}



def capture_with_fallbacks(player=None, *, load_delay: float = 2.0) -> dict:
    """iCSee resilient capture: focus app → web portal → RTSP → fullscreen."""
    errors = []
    # 1) desktop iCSee + screen
    try:
        open_icsee(player=player)
        time.sleep(max(0.5, float(load_delay)))
        shot = capture_screen_png()
        if shot.get("ok") and shot.get("png"):
            shot["strategy"] = "icsee_desktop"
            return shot
        errors.append(shot.get("reason") or "desktop_fail")
    except Exception as e:
        errors.append(f"desktop:{e}")
    # 2) web portal
    try:
        import actions.web_media.browser_control as browser_control
        browser_control.browser_control(parameters={"action": "open", "url": env("ICSEE_WEB_URL", DEFAULT_ICSEE_WEB)})
        time.sleep(2.0)
        shot = capture_screen_png()
        if shot.get("ok") and shot.get("png"):
            shot["strategy"] = "icsee_web"
            return shot
        errors.append(shot.get("reason") or "web_fail")
    except Exception as e:
        errors.append(f"web:{e}")
    # 3) RTSP single frame
    rtsp = env("ICSEE_RTSP_URL")
    if rtsp:
        try:
            import cv2
            cap = cv2.VideoCapture(rtsp)
            try:
                ok, frame = cap.read()
                if ok and frame is not None:
                    ok2, buf = cv2.imencode(".png", frame)
                    if ok2:
                        data = buf.tobytes()
                        path = evid_dir() / f"rtsp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                        path.write_bytes(data)
                        return {"ok": True, "png": data, "path": str(path), "strategy": "rtsp"}
            finally:
                cap.release()
        except Exception as e:
            errors.append(f"rtsp:{e}")
    # 4) fullscreen last resort
    try:
        shot = capture_screen_png()
        if shot.get("ok") and shot.get("png"):
            shot["strategy"] = "fullscreen"
            return shot
        errors.append(shot.get("reason") or "fullscreen_fail")
    except Exception as e:
        errors.append(f"fullscreen:{e}")
    return {"ok": False, "reason": "all_capture_strategies_failed", "errors": errors[:6]}


def load_camera_rois() -> dict:
    path = _BASE / "config" / "camera_rois.json"
    try:
        import json as _json
        return _json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"cameras": {}}


def apply_roi_mask(png_bytes: bytes, camera_id: str = "gate") -> tuple[bytes, list[str]]:
    """Black-out pixels outside ROI polygons. Returns (masked_png, zone_names)."""
    zones: list[str] = []
    try:
        import numpy as np
        import cv2
        arr = np.frombuffer(png_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return png_bytes, zones
        h, w = img.shape[:2]
        rois = (load_camera_rois().get("cameras") or {}).get(camera_id) or {}
        polys = rois.get("polygons") or []
        if not polys:
            return png_bytes, zones
        mask = np.zeros((h, w), dtype=np.uint8)
        for poly in polys:
            pts = poly.get("points") or []
            if len(pts) < 3:
                continue
            zones.append(str(poly.get("zone") or "zona"))
            pts_px = np.array([[int(float(x) * w), int(float(y) * h)] for x, y in pts], dtype=np.int32)
            cv2.fillPoly(mask, [pts_px], 255)
        masked = img.copy()
        masked[mask == 0] = 0
        ok, buf = cv2.imencode(".png", masked)
        if ok:
            return buf.tobytes(), zones
    except Exception as e:
        audit("roi_mask_fail", extra={"error": str(e)[:120]})
    return png_bytes, zones


def point_in_rois(x_norm: float, y_norm: float, camera_id: str = "gate") -> list[str]:
    """Return zone names containing normalized point."""
    hit = []
    try:
        rois = (load_camera_rois().get("cameras") or {}).get(camera_id) or {}
        for poly in rois.get("polygons") or []:
            pts = poly.get("points") or []
            if len(pts) < 3:
                continue
            # ray casting
            inside = False
            j = len(pts) - 1
            for i in range(len(pts)):
                xi, yi = float(pts[i][0]), float(pts[i][1])
                xj, yj = float(pts[j][0]), float(pts[j][1])
                if ((yi > y_norm) != (yj > y_norm)) and (
                    x_norm < (xj - xi) * (y_norm - yi) / (yj - yi + 1e-9) + xi
                ):
                    inside = not inside
                j = i
            if inside:
                hit.append(str(poly.get("zone") or "zona"))
    except Exception:
        pass
    return hit


# ── Tripwire / Object tracking ───────────────────────────────────────────────

class ObjectTracker:
    """Lightweight centroid tracker across consecutive frames (normalized coords)."""

    def __init__(self, max_dist: float = 0.12):
        self.max_dist = max_dist
        self._prev: list[tuple[float, float]] = []
        self._tracks: list[dict] = []  # {id, points: [(x,y),...]}
        self._next_id = 1

    def update(self, centroids: list[tuple[float, float]]) -> list[dict]:
        import math
        assigned = []
        used_prev = set()
        for c in centroids:
            best_i, best_d = None, 1e9
            for i, p in enumerate(self._prev):
                if i in used_prev:
                    continue
                d = math.hypot(c[0] - p[0], c[1] - p[1])
                if d < best_d and d <= self.max_dist:
                    best_d, best_i = d, i
            if best_i is not None:
                used_prev.add(best_i)
                # find track ending at prev
                tr = None
                for t in self._tracks:
                    if t["points"] and t["points"][-1] == self._prev[best_i]:
                        tr = t
                        break
                if tr is None:
                    tr = {"id": self._next_id, "points": [self._prev[best_i]]}
                    self._next_id += 1
                    self._tracks.append(tr)
                tr["points"].append(c)
                assigned.append(tr)
            else:
                tr = {"id": self._next_id, "points": [c]}
                self._next_id += 1
                self._tracks.append(tr)
                assigned.append(tr)
        self._prev = list(centroids)
        # prune long tracks
        self._tracks = [t for t in self._tracks if len(t["points"]) < 60]
        return assigned


def _orient(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(p1, p2, q1, q2) -> bool:
    o1, o2 = _orient(p1, p2, q1), _orient(p1, p2, q2)
    o3, o4 = _orient(q1, q2, p1), _orient(q1, q2, p2)
    return (o1 * o2 < 0) and (o3 * o4 < 0)


def classify_tripwire_crossing(
    prev_pt: tuple[float, float],
    curr_pt: tuple[float, float],
    p1: list,
    p2: list,
    intrusion_direction: str = "outside_to_inside",
) -> str:
    """Return intrusion | exit | passby based on segment cross + direction."""
    a = (float(p1[0]), float(p1[1]))
    b = (float(p2[0]), float(p2[1]))
    if not _segments_intersect(prev_pt, curr_pt, a, b):
        # parallel / no cross
        return "passby"
    # side of line before vs after using cross product sign
    cross = _orient(a, b, curr_pt)
    # intrusion_direction outside_to_inside: positive cross means "inside" side heuristic
    if intrusion_direction == "outside_to_inside":
        return "intrusion" if cross > 0 else "exit"
    if intrusion_direction == "inside_to_outside":
        return "exit" if cross > 0 else "intrusion"
    return "intrusion" if cross > 0 else "exit"


def evaluate_tripwires(
    camera_id: str,
    prev_centroid: tuple[float, float] | None,
    curr_centroid: tuple[float, float] | None,
) -> list[dict]:
    if not prev_centroid or not curr_centroid:
        return []
    rois = (load_camera_rois().get("cameras") or {}).get(camera_id) or {}
    results = []
    for tw in rois.get("tripwires") or []:
        p1, p2 = tw.get("p1"), tw.get("p2")
        if not p1 or not p2:
            continue
        cls = classify_tripwire_crossing(
            prev_centroid, curr_centroid, p1, p2, str(tw.get("intrusion_direction") or "outside_to_inside")
        )
        if cls == "passby":
            continue
        event = {
            "camera_id": camera_id,
            "tripwire_name": tw.get("name") or "tripwire",
            "direction": tw.get("intrusion_direction"),
            "classification": cls,
            "prev": prev_centroid,
            "curr": curr_centroid,
        }
        results.append(event)
        try:
            from core.event_bus import publish as _eb
            _eb("vision.tripwire_crossed", **event)
        except Exception:
            pass
        audit("tripwire_crossed", extra=event)
    return results


class MotionSubtractor:
    """Adaptive background subtractor wrapper (MOG2 if OpenCV present, else frame diff)."""

    def __init__(self):
        self._mog = None
        self._prev = None
        try:
            import cv2
            self._mog = cv2.createBackgroundSubtractorMOG2(history=120, varThreshold=16, detectShadows=True)
        except Exception:
            self._mog = None

    def apply(self, frame_bgr) -> Any:
        import numpy as np
        if self._mog is not None:
            return self._mog.apply(frame_bgr)
        gray = frame_bgr
        try:
            import cv2
            if len(frame_bgr.shape) == 3:
                gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        except Exception:
            gray = frame_bgr
        if self._prev is None:
            self._prev = gray
            return np.zeros_like(gray)
        diff = np.abs(gray.astype("int16") - self._prev.astype("int16")).astype("uint8")
        self._prev = gray
        return (diff > 25).astype("uint8") * 255


def morphological_clean(mask, k: int = 3):
    try:
        import cv2
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        return mask
    except Exception:
        return mask


def centroids_from_mask(mask, min_area: int = 400) -> list[tuple[float, float]]:
    """Return normalized centroids of connected components."""
    cents = []
    try:
        import cv2
        import numpy as np
        h, w = mask.shape[:2]
        n, labels, stats, centroids = cv2.connectedComponentsWithStats((mask > 0).astype("uint8"), connectivity=8)
        for i in range(1, n):
            area = int(stats[i, cv2.CC_STAT_AREA])
            if area < min_area:
                continue
            x, y = float(centroids[i][0]) / w, float(centroids[i][1]) / h
            cents.append((x, y))
    except Exception:
        pass
    return cents


def lbp_histogram(gray_img, bins: int = 16) -> list[float]:
    """Simplified LBP histogram for offline face comparison (no sklearn)."""
    try:
        import numpy as np
        g = gray_img
        if g.ndim == 3:
            g = g.mean(axis=2)
        g = g.astype("uint8")
        h, w = g.shape
        codes = []
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                c = int(g[y, x])
                bits = [
                    g[y - 1, x - 1] >= c,
                    g[y - 1, x] >= c,
                    g[y - 1, x + 1] >= c,
                    g[y, x + 1] >= c,
                    g[y + 1, x + 1] >= c,
                    g[y + 1, x] >= c,
                    g[y + 1, x - 1] >= c,
                    g[y, x - 1] >= c,
                ]
                code = sum(int(b) << i for i, b in enumerate(bits))
                codes.append(code)
        hist, _ = np.histogram(codes, bins=bins, range=(0, 256), density=True)
        return [float(x) for x in hist]
    except Exception:
        return [0.0] * bins


def hist_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    # correlation-like
    import math
    ma = sum(a) / len(a)
    mb = sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a)) or 1e-9
    db = math.sqrt(sum((y - mb) ** 2 for y in b)) or 1e-9
    return max(0.0, min(1.0, num / (da * db)))
