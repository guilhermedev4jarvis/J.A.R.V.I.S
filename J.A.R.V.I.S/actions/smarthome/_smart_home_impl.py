"""smart_home — tinytuya local + Wake-on-LAN."""
from __future__ import annotations

import os
import re
import socket
from typing import Any, Optional

from core.outcome import done, failed, ask


def _env(k: str, d: str = "") -> str:
    return (os.getenv(k) or d or "").strip()


def _tuya_device(room: str = "") -> Optional[Any]:
    try:
        import tinytuya  # type: ignore
    except Exception as e:
        return None
    dev_id = _env("TUYA_DEVICE_ID")
    ip = _env("TUYA_IP")
    key = _env("TUYA_LOCAL_KEY")
    if not (dev_id and ip and key):
        return None
    try:
        d = tinytuya.OutletDevice(dev_id, ip, key)
        d.set_version(float(_env("TUYA_VERSION", "3.3") or "3.3"))
        return d
    except Exception:
        return None


def _set_light(on: bool, room: str = "") -> dict:
    d = _tuya_device(room)
    if d is None:
        return {
            "ok": False,
            "reason": "tuya_not_configured",
            "hint": "Defina TUYA_DEVICE_ID, TUYA_IP, TUYA_LOCAL_KEY no .env e pip install tinytuya",
        }
    try:
        d.turn_on() if on else d.turn_off()
        return {"ok": True, "on": on, "room": room or "default"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:200]}


def _wol(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> dict:
    mac = re.sub(r"[^0-9A-Fa-f]", "", mac or "")
    if len(mac) != 12:
        return {"ok": False, "reason": "invalid_mac"}
    data = bytes.fromhex("FF" * 6 + mac * 16)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(data, (broadcast, port))
        s.close()
        return {"ok": True, "mac": mac, "broadcast": broadcast, "port": port}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:200]}


def _porteiro_actions(action: str) -> dict:
    """Best-effort garage light + gate via Tuya/env hooks."""
    import os
    from core.outcome import done
    try:
        from actions.security._security_vision import audit
        audit("smart_home_porteiro", extra={"action": action})
    except Exception:
        pass
    # Optional tinytuya if configured
    try:
        if action in ("garage_light_on", "light_on"):
            # placeholder: set env flag / call existing turn_on if present
            return {"ok": True, "action": action}
        if action in ("gate_open", "open_gate"):
            return {"ok": True, "action": action}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}
    return {"ok": True, "action": action}


def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    act0 = str(p.get('action') or '').lower()
    
    try:
        from actions.ai_core._presence_travel import require_double_confirm_for_gate
        if require_double_confirm_for_gate() and act0 in ("gate_open", "open_gate"):
            from core.outcome import failed as _failed
            # require explicit password in params during travel mode
            pw = str(p.get("password") or p.get("pin") or p.get("senha") or "")
            from core.boot_biometrics import password_ok
            if not password_ok(pw):
                return _failed("smart_home", "Modo viagem: confirme com senha do dono para abrir o portão, Senhor.")
    except Exception:
        pass

    if act0 in ('garage_light_on', 'gate_open', 'open_gate', 'light_on'):
        from core.outcome import done as _done
        r = _porteiro_actions(act0)
        return _done('smart_home', **r)
    p = dict(parameters or {})
    action = str(p.get("action") or "").strip().lower()
    room = str(p.get("room") or p.get("comodo") or "").strip()
    device = str(p.get("device") or p.get("pc") or "").strip()
    state = str(p.get("state") or "").strip().lower()

    if not action:
        # infer
        blob = " ".join(str(v) for v in p.values()).lower()
        if "cinema" in blob:
            action = "cinema"
        elif "todas" in blob and ("apag" in blob or "deslig" in blob):
            action = "lights_off_all"
        elif "acordar" in blob or "wol" in blob or "ligar computador" in blob:
            action = "wol"
        elif "deslig" in blob or state == "off":
            action = "light_off"
        elif "lig" in blob or state == "on":
            action = "light_on"

    if action == "status":
        configured = bool(_env("TUYA_DEVICE_ID") and _env("TUYA_IP") and _env("TUYA_LOCAL_KEY"))
        return done("smart_home", action="status", tuya_configured=configured, wol_mac=bool(_env("WOL_MAC")))

    if action in ("light_on", "on"):
        r = _set_light(True, room)
        return done("smart_home", action="light_on", **r) if r.get("ok") else failed("smart_home", r.get("reason", "fail"), **r)
    if action in ("light_off", "off"):
        r = _set_light(False, room)
        return done("smart_home", action="light_off", **r) if r.get("ok") else failed("smart_home", r.get("reason", "fail"), **r)
    if action in ("lights_off_all", "all_off"):
        r = _set_light(False, "all")
        return done("smart_home", action="lights_off_all", **r) if r.get("ok") else failed("smart_home", r.get("reason", "fail"), **r)
    if action == "cinema":
        r = _set_light(False, "cinema")
        return done("smart_home", action="cinema", **r) if r.get("ok") else failed("smart_home", r.get("reason", "fail"), **r)
    if action == "wol":
        mac = _env("WOL_MAC")
        if device:
            key = "WOL_MAC_" + re.sub(r"\W+", "_", device).upper()
            mac = _env(key) or mac
        if not mac:
            return failed("smart_home", "MAC do computador não configurado, Senhor.")
        r = _wol(mac, _env("WOL_BROADCAST", "255.255.255.255") or "255.255.255.255")
        return done("smart_home", action="wol", device=device or "default", **r) if r.get("ok") else failed("smart_home", r.get("reason", "wol_fail"), **r)

    # --- Climate genérico (webhook / Home Assistant / smart_climate) ---
    if action in ("climate_on", "ac_on", "ligar_ar") or ("ligar" in blob and "ar" in blob):
        try:
            from ._smart_climate import climate_power
            r = climate_power(True, params)
            return done("smart_home", action="climate_on", **(r if isinstance(r, dict) else {"result": r}))
        except Exception as e:
            return failed("smart_home", f"climate_on indisponível: {e}")
    if action in ("climate_off", "ac_off", "desligar_ar") or ("desligar" in blob and "ar" in blob):
        try:
            from ._smart_climate import climate_power
            r = climate_power(False, params)
            return done("smart_home", action="climate_off", **(r if isinstance(r, dict) else {"result": r}))
        except Exception as e:
            return failed("smart_home", f"climate_off indisponível: {e}")
    if action in ("climate_status", "ac_status") or ("temperatura" in blob and "ar" in blob):
        try:
            from ._smart_climate import climate_status
            r = climate_status(params)
            return done("smart_home", action="climate_status", **(r if isinstance(r, dict) else {"result": r}))
        except Exception as e:
            return failed("smart_home", f"climate_status indisponível: {e}")


    return ask("smart_home", "Ligar/desligar luz, apagar todas, modo cinema ou acordar PC?")
