"""leitor_placas_alpr — OCR de placa + known_vehicles + EventBus."""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Optional

from core.outcome import ask, done, failed
from core.resilience import atomic_write_json, safe_read_json, sanitize_plate
from ._security_vision import (
    audit,
    capture_with_fallbacks,
    speak_short,
)

_BASE = Path(__file__).resolve().parents[2]
_PATH = _BASE / "memory" / "veiculos_conhecidos.json"
_CFG = _BASE / "config" / "known_vehicles.json"
_lock = threading.Lock()

try:
    from core.event_bus import publish as _eb_pub
except Exception:
    def _eb_pub(*_a, **_k):
        pass
from ._porteiro_inteligente import note_unknown_plate, enrich_plate_event_night
from actions.smarthome._smart_climate import on_trusted_vehicle_arrival


def _confusions(s: str) -> list[str]:
    """Generate OCR confusion variants for BR plates."""
    table = {"O": "0", "0": "O", "I": "1", "1": "I", "S": "5", "5": "S", "B": "8", "8": "B"}
    s = sanitize_plate(s)
    out = {s}
    chars = list(s)
    for i, ch in enumerate(chars):
        if ch in table:
            alt = chars[:]
            alt[i] = table[ch]
            out.add("".join(alt))
    return list(out)


def _normalize_plate(raw: str) -> str:
    p = sanitize_plate(raw)
    # Mercosul AAA0A00 or old AAA0000
    m = re.match(r"^([A-Z]{3})(\d)([A-Z0-9])(\d{2})$", p)
    if m:
        return p
    m = re.match(r"^([A-Z]{3})(\d{4})$", p)
    if m:
        return p
    return p


def _load_memory() -> dict:
    data = safe_read_json(_PATH, default={"vehicles": {}})
    return data if isinstance(data, dict) else {"vehicles": {}}


def _load_config_vehicles() -> list[dict]:
    data = safe_read_json(_CFG, default={"vehicles": []})
    return list((data or {}).get("vehicles") or [])


def _lookup(plate: str) -> Optional[dict]:
    plate_n = _normalize_plate(plate)
    variants = set(_confusions(plate_n))
    variants.add(plate_n)
    # config list
    for v in _load_config_vehicles():
        vp = _normalize_plate(str(v.get("plate") or ""))
        if vp in variants or any(x in _confusions(vp) for x in variants):
            return {
                "plate": vp,
                "model": v.get("model"),
                "owner": v.get("owner"),
                "trust_level": v.get("trust_level") or "trusted",
                "name": f"{v.get('model')} — {v.get('owner')}",
                "source": "config",
            }
    # memory map
    mem = _load_memory().get("vehicles") or {}
    for k, info in mem.items():
        kn = _normalize_plate(k)
        if kn in variants:
            return {
                "plate": kn,
                "name": (info or {}).get("name") or kn,
                "model": (info or {}).get("model"),
                "owner": (info or {}).get("owner") or (info or {}).get("name"),
                "trust_level": (info or {}).get("trust_level") or "known",
                "source": "memory",
            }
    return None


def _save_memory(data: dict) -> None:
    with _lock:
        atomic_write_json(_PATH, data)


def _register_config(plate: str, model: str, owner: str) -> None:
    data = safe_read_json(_CFG, default={"vehicles": []})
    vehicles = list(data.get("vehicles") or [])
    plate_n = _normalize_plate(plate)
    vehicles = [v for v in vehicles if _normalize_plate(str(v.get("plate") or "")) != plate_n]
    vehicles.append(
        {
            "plate": plate_n,
            "model": model or "Veículo",
            "owner": owner or "Casa",
            "trust_level": "trusted",
            "notify_on_arrival": True,
        }
    )
    data["vehicles"] = vehicles
    atomic_write_json(_CFG, data)


def _vision_plate(png: bytes) -> dict:
    prompt = (
        "Imagem de câmera de portão. Extraia placa (padrão BR Mercosul AAA0A00 ou antigo AAA0000), "
        "modelo e cor. JSON: {\"placa\":\"...\",\"modelo\":\"...\",\"cor\":\"...\",\"descricao\":\"...\"}."
    )
    raw = ""
    try:
        from core import gemini as gem
        from google.genai import types as gtypes
        key = gem.api_key() if hasattr(gem, "api_key") else ""
        if key:
            part = gtypes.Part.from_bytes(data=png, mime_type="image/png")
            raw = gem.text([prompt, part], timeout_ms=25000, key=key) or ""
    except Exception as e:
        audit("alpr_gemini_fail", tool="leitor_placas_alpr", extra={"error": str(e)[:100]})
    if not raw:
        try:
            from core.llm_client import call_llm_text
            raw = call_llm_text(prompt, system="JSON only", timeout=20) or ""
        except Exception:
            pass
    data = {"placa": "", "modelo": "", "cor": "", "descricao": (raw or "")[:200]}
    if raw:
        try:
            s, e = raw.find("{"), raw.rfind("}")
            if s >= 0 and e > s:
                data.update(json.loads(raw[s : e + 1]))
        except Exception:
            m = re.search(r"[A-Z]{3}\d[A-Z0-9]\d{2}|[A-Z]{3}-?\d{4}", raw.upper())
            if m:
                data["placa"] = m.group(0).replace("-", "")
    data["placa"] = _normalize_plate(str(data.get("placa") or ""))
    return data


def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "read").lower()
    if action == "list":
        cfg = _load_config_vehicles()
        mem = _load_memory().get("vehicles") or {}
        return done("leitor_placas_alpr", config=cfg, memory=mem)
    if action == "remove":
        plate = _normalize_plate(str(p.get("plate") or p.get("text") or ""))
        if not plate:
            return ask("leitor_placas_alpr", "Qual placa remover, Senhor?")
        data = _load_memory()
        data.get("vehicles", {}).pop(plate, None)
        _save_memory(data)
        cfg = safe_read_json(_CFG, default={"vehicles": []})
        cfg["vehicles"] = [v for v in cfg.get("vehicles") or [] if _normalize_plate(str(v.get("plate") or "")) != plate]
        atomic_write_json(_CFG, cfg)
        speak_short("Placa removida, Senhor.", player=player)
        return done("leitor_placas_alpr", action="remove", plate=plate)
    if action == "register":
        plate = _normalize_plate(str(p.get("plate") or p.get("text") or ""))
        name = str(p.get("name") or "").strip()
        model = str(p.get("model") or name or "Veículo").strip()
        owner = str(p.get("owner") or name or "Casa").strip()
        if not plate:
            return ask("leitor_placas_alpr", "Informe placa e nome, Senhor.")
        data = _load_memory()
        data.setdefault("vehicles", {})[plate] = {"name": name or owner, "model": model, "owner": owner}
        _save_memory(data)
        _register_config(plate, model, owner)
        speak_short(f"Placa {plate} cadastrada, Senhor.", player=player)
        return done("leitor_placas_alpr", action="register", plate=plate, model=model, owner=owner)

    speak_short("Analisando o portão, Senhor.", player=player)
    cap = capture_with_fallbacks(player=player, load_delay=2.0)
    if not cap.get("ok") or not cap.get("png"):
        from ._security_vision import frames_from_folder
        root = _BASE / "memory" / "teste_cameras"
        frames = frames_from_folder(root, count=1)
        if frames and frames[0].get("_png"):
            cap = {"ok": True, "png": frames[0]["_png"], "path": frames[0].get("path")}
        else:
            return failed("leitor_placas_alpr", "sem imagem do portão")
    info = _vision_plate(cap["png"])
    plate = _normalize_plate(str(info.get("placa") or ""))
    known = _lookup(plate) if plate else None
    is_known = bool(known)
    vehicle_info = ""
    if known:
        vehicle_info = f"{known.get('model') or ''} - {known.get('owner') or known.get('name') or ''}".strip(" -")
        speak_short(f"Veículo conhecido: {vehicle_info}, placa {plate}.", player=player)
    elif plate:
        speak_short(f"Veículo desconhecido, placa {plate}.", player=player)
    else:
        speak_short("Não identifiquei a placa com clareza, Senhor.", player=player)

    evt = enrich_plate_event_night({
        "plate": plate,
        "is_known_vehicle": is_known,
        "vehicle_info": vehicle_info or str(info.get("modelo") or ""),
        "camera_id": "gate",
        "trust_level": (known or {}).get("trust_level"),
    })
    _eb_pub("alpr.plate_detected", **evt)
    if plate and not is_known:
        note_unknown_plate(plate, snapshot_path=cap.get("path"))
    if plate and is_known:
        try:
            on_trusted_vehicle_arrival(plate, True)
        except Exception:
            pass
    return done(
        "leitor_placas_alpr",
        action="read",
        **info,
        known=known,
        is_known_vehicle=is_known,
        vehicle_info=vehicle_info,
        path=cap.get("path"),
    )
