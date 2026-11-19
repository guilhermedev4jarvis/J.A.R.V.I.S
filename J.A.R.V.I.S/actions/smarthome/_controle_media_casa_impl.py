
"""controle_media_casa — teclas de mídia + atalhos YouTube/Spotify."""
from __future__ import annotations
import webbrowser
from urllib.parse import quote_plus
from core.outcome import done, failed, ask
from actions.security._security_vision import speak_short

def _key(name: str) -> dict:
    try:
        import pyautogui
        pyautogui.press(name)
        return {"ok": True, "key": name}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}

def run(parameters=None, player=None, **_ctx) -> str:
    p = dict(parameters or {})
    action = str(p.get("action") or "").lower()
    q = str(p.get("query") or p.get("text") or "").strip()
    if not action:
        blob = " ".join(str(v) for v in p.values()).lower()
        if "aument" in blob or "subir" in blob: action = "volume_up"
        elif "diminu" in blob or "abaix" in blob: action = "volume_down"
        elif "desmut" in blob: action = "unmute"
        elif "mut" in blob: action = "mute"
        elif "próxim" in blob or "proxim" in blob or "next" in blob: action = "next"
        elif "paus" in blob or "play" in blob: action = "play_pause"
        elif "youtube" in blob: action = "youtube"
        elif "spotify" in blob: action = "spotify"
    map_keys = {
        "volume_up": "volumeup", "volume_down": "volumedown",
        "mute": "volumemute", "unmute": "volumemute",
        "play_pause": "playpause", "next": "nexttrack", "previous": "prevtrack",
    }
    if action in map_keys:
        r = _key(map_keys[action])
        if r.get("ok"):
            speak_short("Feito, Senhor.", player=player)
            return done("controle_media_casa", action=action, **r)
        return failed("controle_media_casa", r.get("reason", "fail"))
    if action == "youtube":
        url = "https://www.youtube.com"
        if q:
            url = f"https://www.youtube.com/results?search_query={quote_plus(q)}"
        webbrowser.open(url)
        speak_short("YouTube aberto, Senhor.", player=player)
        return done("controle_media_casa", action="youtube", query=q)
    if action == "spotify":
        webbrowser.open("https://open.spotify.com" + (f"/search/{quote_plus(q)}" if q else ""))
        speak_short("Spotify aberto, Senhor.", player=player)
        return done("controle_media_casa", action="spotify", query=q)
    return ask("controle_media_casa", "Volume, mídia ou YouTube, Senhor?")
