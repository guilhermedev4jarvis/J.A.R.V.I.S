"""
core/retry.py — exponential backoff + circuit breaker for flaky tools.

Tools that talk to the network, the OS UI, or external apps fail for transient
reasons (window not focused yet, DNS blip, rate limit). Blind retries hide
bugs; no retries make the assistant look broken. This module is the middle path:

    with circuit_breaker("browser_control") as gate:
        if not gate.allow():
            return failed("browser_control", "circuit open — cooling down")
        result = retry_call(fn, attempts=3, base_delay=0.4)
        gate.record(success=not is_problem(result))

Circuit state is process-local (not shared across restarts). That is intentional:
a fresh session should get a clean slate.
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")

# Defaults tuned for desktop automation, not high-QPS APIs.
_DEFAULT_ATTEMPTS = 3
_DEFAULT_BASE_DELAY = 0.35
_DEFAULT_MAX_DELAY = 4.0
_DEFAULT_FAILURE_THRESHOLD = 5
_DEFAULT_RESET_SECONDS = 45.0


@dataclass
class _BreakerState:
    failures: int = 0
    opened_at: float = 0.0
    half_open: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


_BREAKERS: dict[str, _BreakerState] = {}
_BREAKERS_LOCK = threading.Lock()


def _state(name: str) -> _BreakerState:
    with _BREAKERS_LOCK:
        if name not in _BREAKERS:
            _BREAKERS[name] = _BreakerState()
        return _BREAKERS[name]


class CircuitOpenError(RuntimeError):
    """Raised when the circuit is open and the call is rejected."""


class CircuitGate:
    """Per-tool gate returned by ``circuit_breaker``."""

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
        reset_seconds: float = _DEFAULT_RESET_SECONDS,
    ):
        self.name = name
        self.failure_threshold = max(1, failure_threshold)
        self.reset_seconds = max(1.0, reset_seconds)
        self._state = _state(name)

    def allow(self) -> bool:
        st = self._state
        with st.lock:
            if st.failures < self.failure_threshold:
                return True
            elapsed = time.monotonic() - st.opened_at
            if elapsed >= self.reset_seconds:
                st.half_open = True
                return True  # single probe
            return False

    def record(self, success: bool) -> None:
        st = self._state
        with st.lock:
            if success:
                st.failures = 0
                st.half_open = False
                st.opened_at = 0.0
            else:
                st.failures += 1
                if st.failures >= self.failure_threshold:
                    st.opened_at = time.monotonic()
                    st.half_open = False

    def status(self) -> dict[str, Any]:
        st = self._state
        with st.lock:
            open_ = st.failures >= self.failure_threshold and not st.half_open
            return {
                "name": self.name,
                "failures": st.failures,
                "open": open_,
                "half_open": st.half_open,
                "threshold": self.failure_threshold,
            }


class circuit_breaker:
    """Context manager that yields a CircuitGate."""

    def __init__(self, name: str, **kwargs: Any):
        self.gate = CircuitGate(name, **kwargs)

    def __enter__(self) -> CircuitGate:
        return self.gate

    def __exit__(self, *exc: Any) -> None:
        return None


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = _DEFAULT_ATTEMPTS,
    base_delay: float = _DEFAULT_BASE_DELAY,
    max_delay: float = _DEFAULT_MAX_DELAY,
    retry_on: Optional[Callable[[BaseException], bool]] = None,
    retry_if_result: Optional[Callable[[T], bool]] = None,
    jitter: bool = True,
) -> T:
    """Call ``fn`` up to ``attempts`` times with exponential backoff.

    Parameters
    ----------
    retry_on
        Predicate on the exception. Default: retry on any Exception.
    retry_if_result
        If the call succeeds but the result still looks transient (e.g. status=
        failed with "timeout"), return True to retry.
    """
    attempts = max(1, int(attempts))
    last_exc: Optional[BaseException] = None
    last_result: Any = None

    for i in range(attempts):
        try:
            result = fn()
            if retry_if_result is not None and i < attempts - 1 and retry_if_result(result):
                last_result = result
                _sleep(base_delay, max_delay, i, jitter)
                continue
            return result
        except BaseException as e:  # noqa: BLE001 — intentional boundary
            last_exc = e
            should = retry_on(e) if retry_on is not None else isinstance(e, Exception)
            if not should or i >= attempts - 1:
                raise
            _sleep(base_delay, max_delay, i, jitter)

    if last_exc is not None:
        raise last_exc
    return last_result  # type: ignore[return-value]


def _sleep(base: float, max_delay: float, attempt: int, jitter: bool) -> None:
    delay = min(max_delay, base * (2 ** attempt))
    if jitter:
        delay = delay * (0.5 + random.random())
    time.sleep(delay)


def reset_circuit(name: str) -> None:
    """Clear breaker state (tests / manual recovery)."""
    with _BREAKERS_LOCK:
        _BREAKERS.pop(name, None)


def all_circuits() -> list[dict[str, Any]]:
    with _BREAKERS_LOCK:
        names = list(_BREAKERS.keys())
    return [CircuitGate(n).status() for n in names]
