from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any


_SAFE_TEXT_PATTERN = re.compile(r'[^a-zA-Z0-9@._:/+\-\s]')
_SAFE_SLUG_PATTERN = re.compile(r'[^a-z0-9-]')
_EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class RateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            entries = self._requests[key]
            while entries and entries[0] < cutoff:
                entries.popleft()
            if len(entries) >= limit:
                retry_after = max(int(window_seconds - (now - entries[0])), 1)
                return False, retry_after
            entries.append(now)
        return True, 0


class RedisRateLimiter:
    def __init__(self, client, prefix: str = 'coreflow:ratelimit', fallback: RateLimiter | None = None):
        self.client = client
        self.prefix = prefix
        self.fallback = fallback or RateLimiter()

    def check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        bucket = int(time.time() // max(window_seconds, 1))
        redis_key = f'{self.prefix}:{bucket}:{key}'
        try:
            pipeline = self.client.pipeline()
            pipeline.incr(redis_key)
            pipeline.expire(redis_key, window_seconds + 1)
            pipeline.ttl(redis_key)
            count, _, ttl = pipeline.execute()
            if int(count) > limit:
                return False, max(int(ttl), 1)
            return True, 0
        except Exception:
            return self.fallback.check(key, limit, window_seconds)


def sanitize_text(value: str, max_length: int = 120) -> str:
    normalized = ' '.join((value or '').strip().split())
    normalized = _SAFE_TEXT_PATTERN.sub('', normalized)
    return normalized[:max_length]


def sanitize_slug(value: str) -> str:
    normalized = value.strip().lower().replace(' ', '-')
    normalized = _SAFE_SLUG_PATTERN.sub('', normalized)
    normalized = re.sub(r'-{2,}', '-', normalized).strip('-')
    if not normalized:
        raise ValueError('Slug cannot be empty after sanitization.')
    return normalized[:80]


def sanitize_email(value: str) -> str:
    normalized = value.strip().lower()
    if not _EMAIL_PATTERN.match(normalized):
        raise ValueError('Invalid email address.')
    return normalized[:160]


def sanitize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {sanitize_text(str(key), 60): sanitize_metadata(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_metadata(item) for item in value[:50]]
    if isinstance(value, str):
        return sanitize_text(value, 240)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname.lower(),
            'logger': record.name,
            'message': record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith('_') or key in {'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename', 'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName', 'created', 'msecs', 'relativeCreated', 'thread', 'threadName', 'processName', 'process', 'message'}:
                continue
            payload[key] = sanitize_metadata(value)
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_structured_logging() -> None:
    root = logging.getLogger()
    if any(getattr(handler, '_coreflow_structured', False) for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    handler._coreflow_structured = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(logging.INFO)
