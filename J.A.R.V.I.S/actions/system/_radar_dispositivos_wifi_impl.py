
"""radar_dispositivos_wifi — ARP scan + dispositivos conhecidos."""
from __future__ import annotations
import json, re, subprocess, threading, time
from pathlib import Path
from typing import Any
from core.outcome import done, ask
from actions.security._security_vision import audit, send_telegram, speak_short
try:
    from core.event_bus import publish as _eb_pub
except Exception:
    def _eb_pub(*a, **k): pass
from actions.ai_core._presence_travel import update_presence

_PATH = Path(__file__).resolve().parents[2] / "memory" / "dispositivos_conhecidos.json"
_lock = threading.Lock()
_alert = {"thread": None, "stop": threading.Event(), "seen": set()}

def _load() -> dict:
    if not _PATH.is_file():
        return {"devices": {}}
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"devices": {}}

def _save(data: dict) -> None:
    with _lock:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _arp_scan() -> list[dict]:
    out = []
    try:
        r = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=15)
        text = r.stdout or ""
    except Exception as e:
        audit("wifi_arp_fail", tool="radar_dispositivos_wifi", extra={"error": str(e)[:100]})
        return out
    # Windows and unix-ish patterns
    for line in text.splitlines():
        ip = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
        mac = re.search(r"([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}", line)
        if ip and mac:
            m = mac.group(0).lower().replace("-", ":")
            out.append({"ip": ip.group(1), "mac": m})
    return out

def _loop():
    known = _load().get("devices") or {}
    while not _alert["stop"].is_set():
        try:
            for d in _arp_scan():
                mac = d["mac"]
                if mac in _alert["seen"]:
                    continue
                _alert["seen"].add(mac)
                # track current set for left events
                _alert.setdefault("_now", set()).add(mac)
                if mac not in known:
                    msg = f"Novo dispositivo na rede: `{mac}` IP `{d['ip']}`"
                    send_telegram("*Radar Wi-Fi*\n" + msg, markdown=True)
                    audit("wifi_new_device", tool="radar_dispositivos_wifi", extra={"mac": mac})
                    _eb_pub("wifi.device_joined", mac=mac, ip=d.get("ip"), device_name=known.get(mac) or "desconhecido", owner_tag=(known.get(mac) or "").lower())
        except Exception as e:
            audit("wifi_loop_err", tool="radar_dispositivos_wifi", extra={"error": str(e)[:120]})
        # emit left
            prev = _alert.get("_prev_scan") or set()
            now_set = _alert.get("_now") or set()
            for gone in prev - now_set:
                tag = (known.get(gone) or "").lower()
                _eb_pub("wifi.device_left", mac=gone, ip="", device_name=known.get(gone) or "desconhecido", owner_tag=tag)
            _alert["_prev_scan"] = set(now_set)
            _alert["_now"] = set()
            # presence / travel mode
            try:
                update_presence(_arp_scan(), known)
            except Exception:
                pass
            _alert["stop"].wait(120)

def start_alert() -> bool:
    if _alert["thread"] and _alert["thread"].is_alive():
        return True
    _alert["stop"] = threading.Event()
    t = threading.Thread(target=_loop, daemon=True, name="radar-wifi")
    _alert["thread"] = t
    t.start()
    return True

def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "scan").lower()
    if action == "start_alert":
        return done("radar_dispositivos_wifi", alert=start_alert())
    if action == "stop_alert":
        _alert["stop"].set()
        return done("radar_dispositivos_wifi", alert=False)
    if action == "register":
        mac = str(p.get("mac") or "").lower().replace("-", ":")
        name = str(p.get("name") or p.get("text") or "").strip()
        if not mac or not name:
            return ask("radar_dispositivos_wifi", "Informe MAC e nome, Senhor.")
        data = _load()
        data.setdefault("devices", {})[mac] = name
        _save(data)
        speak_short("Dispositivo registrado, Senhor.", player=player)
        return done("radar_dispositivos_wifi", action="register", mac=mac, name=name)
    if action == "list_known":
        return done("radar_dispositivos_wifi", devices=(_load().get("devices") or {}))
    devices = _arp_scan()
    known = _load().get("devices") or {}
    for d in devices:
        d["name"] = known.get(d["mac"], "desconhecido")
    speak_short(f"Encontrei {len(devices)} dispositivos na rede, Senhor.", player=player)
    return done("radar_dispositivos_wifi", action="scan", devices=devices, count=len(devices),
                alert=bool(_alert["thread"] and _alert["thread"].is_alive()))
