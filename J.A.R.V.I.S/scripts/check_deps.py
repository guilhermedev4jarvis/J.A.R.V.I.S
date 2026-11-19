#!/usr/bin/env python3
"""Report which JARVIS dependency groups import cleanly in this environment."""
from __future__ import annotations

import importlib
import sys

GROUPS = {
    "core_ui_audio": ["numpy"],  # sounddevice needs PortAudio at runtime
    "http": ["httpx", "requests", "bs4"],
    "vision": ["PIL", "cv2"],
    "system": ["psutil"],
    "docs": ["pptx", "openpyxl"],
    "optional_local_stt": ["faster_whisper", "vosk"],
    "optional_mcp": ["mcp"],
    "optional_realtime": ["websockets"],
    "optional_chroma": ["chromadb"],
    "google_genai": ["google.genai"],
    "qt": ["PyQt6"],
}

def main() -> int:
    print(f"Python {sys.version.split()[0]}")
    ok_n = fail_n = 0
    for group, mods in GROUPS.items():
        print(f"\n[{group}]")
        for m in mods:
            try:
                importlib.import_module(m)
                print(f"  OK   {m}")
                ok_n += 1
            except Exception as e:
                print(f"  MISS {m}: {type(e).__name__}: {e}")
                fail_n += 1
    # Project modules
    print("\n[jarvis_quality]")
    sys.path.insert(0, str(__file__).rsplit("/scripts", 1)[0] if "/scripts" in __file__ else ".")
    # fix path
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    for m in [
        "core.contracts", "core.retry", "core.sandbox", "core.redaction",
        "core.audit", "core.agent_mode", "core.network_fallback",
        "core.voice_auth", "core.face_auth", "core.llm_client",
    ]:
        try:
            importlib.import_module(m)
            print(f"  OK   {m}")
            ok_n += 1
        except Exception as e:
            print(f"  FAIL {m}: {type(e).__name__}: {e}")
            fail_n += 1

    print(f"\nSummary: {ok_n} ok, {fail_n} missing/failed")
    return 0 if fail_n == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
