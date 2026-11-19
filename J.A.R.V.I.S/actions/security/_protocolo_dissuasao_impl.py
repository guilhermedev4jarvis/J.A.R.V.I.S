
"""protocolo_dissuasao — intimidação ativa (volume, luzes, voz, sirene)."""
from __future__ import annotations
import os, threading, time
from typing import Optional
from core.outcome import done, failed
from ._security_vision import audit, speak_short, env

_state = {"active": False}

def _set_volume_max() -> dict:
    try:
        if os.name == "nt":
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMasterVolumeLevelScalar(1.0, None)
            try:
                volume.SetMute(0, None)
            except Exception:
                pass
            return {"ok": True, "backend": "pycaw"}
    except Exception as e:
        audit("dissuasao_vol_fail", tool="protocolo_dissuasao", extra={"error": str(e)[:120]})
    try:
        import pyautogui
        for _ in range(50):
            pyautogui.press("volumeup")
        return {"ok": True, "backend": "pyautogui"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}

def _siren(seconds: float = 4.0) -> dict:
    try:
        import numpy as np
        import sounddevice as sd
        sr = 22050
        t = np.linspace(0, seconds, int(sr * seconds), False)
        # alternating tone
        wave = 0.35 * np.sin(2 * np.pi * (800 + 400 * (np.floor(t * 4) % 2)) * t)
        sd.play(wave.astype(np.float32), sr)
        sd.wait()
        return {"ok": True, "backend": "sounddevice"}
    except Exception:
        pass
    try:
        if os.name == "nt":
            import winsound
            for f in (800, 1200, 800, 1200):
                winsound.Beep(f, 400)
            return {"ok": True, "backend": "winsound"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    return {"ok": False, "reason": "no_audio_backend"}

def _lights_on() -> dict:
    try:
        import actions.smarthome.smart_home as smart_home
        r = smart_home.smart_home(parameters={"action": "light_on"})
        return {"ok": "status=failed" not in str(r), "result": str(r)[:120]}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}

def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "ativar").lower()
    if action in ("status",):
        return done("protocolo_dissuasao", active=_state["active"])
    if action in ("parar", "stop"):
        _state["active"] = False
        speak_short("Modo dissuasão encerrado, Senhor.", player=player)
        return done("protocolo_dissuasao", action="parar", active=False)
    _state["active"] = True
    audit("dissuasao_start", tool="protocolo_dissuasao")
    vol = _set_volume_max()
    lights = _lights_on()
    phrase = "Atenção. Propriedade monitorada. A polícia já foi acionada."
    speak_short(phrase, player=player)
    sir = _siren(4.0)
    return done("protocolo_dissuasao", action="ativar", volume=vol, lights=lights, siren=sir, spoken=phrase)
