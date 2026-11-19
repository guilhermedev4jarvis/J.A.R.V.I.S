"""
Action: media_control — system media keys (play/pause, next, previous, mute).
"""
from __future__ import annotations

import platform
import time

_SYSTEM = platform.system()


def _log(msg: str, player=None) -> None:
    print(f"[Media] {msg}")
    if player:
        try:
            player.write_log(f"JARVIS: {msg}")
        except Exception:
            pass


def _send_key(action: str) -> tuple[bool, str]:
    """Send a media key. Returns (ok, detail)."""
    action = action.lower().strip()

    # Map to virtual-key / key names
    # Windows VK codes for media keys
    VK = {
        "play": 0xB3,       # VK_MEDIA_PLAY_PAUSE
        "pause": 0xB3,
        "play_pause": 0xB3,
        "next": 0xB0,       # VK_MEDIA_NEXT_TRACK
        "previous": 0xB1,   # VK_MEDIA_PREV_TRACK
        "prev": 0xB1,
        "stop": 0xB2,       # VK_MEDIA_STOP
        "mute": 0xAD,       # VK_VOLUME_MUTE
    }

    if action not in VK and action not in ("play", "pause", "play_pause", "next", "previous", "prev", "stop", "mute"):
        return False, f"Unknown media action '{action}'"

    if _SYSTEM == "Windows":
        try:
            import ctypes
            vk = VK.get(action, VK.get("play_pause"))
            # key down + key up
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP = 2
            return True, action
        except Exception as e:
            return False, str(e)

    # macOS / Linux via pyautogui if available
    try:
        import pyautogui
        mapping = {
            "play": "playpause",
            "pause": "playpause",
            "play_pause": "playpause",
            "next": "nexttrack",
            "previous": "prevtrack",
            "prev": "prevtrack",
            "stop": "stop",
            "mute": "volumemute",
        }
        key = mapping.get(action)
        if not key:
            return False, f"Unsupported action '{action}'"
        pyautogui.press(key)
        return True, action
    except Exception as e:
        return False, str(e)


def media_control_action(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    action = (parameters.get("action") or "play_pause").strip().lower()
    # normalize aliases
    aliases = {
        "playpause": "play_pause",
        "toggle": "play_pause",
        "pular": "next",
        "proxima": "next",
        "próxima": "next",
        "anterior": "previous",
        "voltar": "previous",
        "mudo": "mute",
        "silenciar": "mute",
    }
    action = aliases.get(action, action)

    ok, detail = _send_key(action)
    if not ok:
        msg = f"Sir, media control failed: {detail}"
        _log(msg, player)
        return msg

    labels = {
        "play": "Play",
        "pause": "Pause",
        "play_pause": "Play/Pause toggled",
        "next": "Next track",
        "previous": "Previous track",
        "prev": "Previous track",
        "stop": "Stop",
        "mute": "Mute toggled",
    }
    msg = f"{labels.get(action, action)}."
    _log(msg, player)
    return msg


TOOL = {
    "name": "media_control",
    "description": (
        "Controls system media playback with media keys: play, pause, "
        "play_pause (toggle), next, previous, stop, mute. "
        "Works with Spotify, YouTube, VLC and any app that listens to media keys. "
        "Use when the user says play, pause, next song, previous track, mute music."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "play | pause | play_pause | next | previous | stop | mute. "
                    "Default: play_pause"
                ),
            },
        },
        "required": [],
    },
    "handler": media_control_action,
}
