"""Process lifecycle: AudioRelay, biometrics gate, UI mainloop, graceful stop."""
from __future__ import annotations

import atexit
import logging
import signal
import threading
from typing import Any, Optional

from main.state import SHUTDOWN_EVENT

_log = logging.getLogger("jarvis.lifecycle")


def _ensure_audiorelay_running() -> bool:
    import importlib
    _app = importlib.import_module("main.app")
    return _app._ensure_audiorelay_running()


def _register_shutdown_hooks() -> None:
    def _flag(*_a: Any) -> None:
        SHUTDOWN_EVENT.set()
        print("\n[JARVIS] shutdown signal", flush=True)

    try:
        signal.signal(signal.SIGINT, _flag)
    except Exception:
        pass
    try:
        signal.signal(signal.SIGTERM, _flag)
    except Exception:
        pass

    def _atexit() -> None:
        SHUTDOWN_EVENT.set()
        try:
            from memory.memory_manager import update_memory
            # best-effort flush marker
            update_memory({})
        except Exception:
            pass

    atexit.register(_atexit)


def main() -> None:
    """Primary entry: UI thread + async JarvisLive runner."""
    import importlib
    _app = importlib.import_module("main.app")

    _register_shutdown_hooks()
    # Prefer lifecycle wrapper if app.main still contains full logic
    return _app.main()


__all__ = ["main", "_ensure_audiorelay_running", "_register_shutdown_hooks"]
