from __future__ import annotations

import threading
import time
from typing import Any


class TTLCacheStore:
    def __init__(self, default_ttl_seconds: int = 15):
        self.default_ttl_seconds = default_ttl_seconds
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.monotonic():
                self._entries.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> Any:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        with self._lock:
            self._entries[key] = (time.monotonic() + ttl, value)
        return value

    def invalidate(self, prefix: str | None = None) -> None:
        with self._lock:
            if prefix is None:
                self._entries.clear()
                return
            for key in list(self._entries.keys()):
                if key.startswith(prefix):
                    self._entries.pop(key, None)
