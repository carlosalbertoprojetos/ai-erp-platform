from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar('T')


class CircuitBreakerOpenError(RuntimeError):
    pass


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 3, recovery_timeout_seconds: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self._lock = threading.Lock()
        self._failure_count = 0
        self._opened_until = 0.0

    def execute(self, func: Callable[[], T]) -> T:
        with self._lock:
            if self._opened_until > time.monotonic():
                raise CircuitBreakerOpenError(f'Circuit breaker {self.name} is open.')
        try:
            result = func()
        except Exception:
            with self._lock:
                self._failure_count += 1
                if self._failure_count >= self.failure_threshold:
                    self._opened_until = time.monotonic() + self.recovery_timeout_seconds
            raise
        with self._lock:
            self._failure_count = 0
            self._opened_until = 0.0
        return result


def retry_sync(func: Callable[[], T], attempts: int = 3, backoff_seconds: float = 0.2) -> T:
    last_error: Exception | None = None
    for attempt in range(1, max(attempts, 1) + 1):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            time.sleep(backoff_seconds * attempt)
    if last_error is None:
        raise RuntimeError('Retry operation failed without an exception.')
    raise last_error
