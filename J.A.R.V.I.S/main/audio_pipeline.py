"""Audio helpers and pipeline utilities."""
from __future__ import annotations

from typing import Any

def _pcm_level(samples: Any) -> float:
    import importlib; _app = importlib.import_module("main.app")
    return _app._pcm_level(samples)

def _pcm_visemes(samples: Any, sr: int = 24000) -> Any:
    import importlib; _app = importlib.import_module("main.app")
    return _app._pcm_visemes(samples, sr)

def _enqueue_latest_audio(queue: Any, item: Any) -> None:
    import importlib; _app = importlib.import_module("main.app")
    return _app._enqueue_latest_audio(queue, item)

__all__ = ["_pcm_level", "_pcm_visemes", "_enqueue_latest_audio"]
