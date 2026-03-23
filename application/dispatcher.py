from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from domain.models import RunRequest


class AsyncExecutionJob(BaseModel):
    correlation_id: str
    payload: dict[str, Any]


class InMemoryExecutionDispatcher:
    backend_name = "memory"

    def __init__(self, max_concurrent_jobs: int = 4):
        self.max_concurrent_jobs = max_concurrent_jobs
        self._semaphore = asyncio.Semaphore(max_concurrent_jobs)
        self._tasks: dict[str, asyncio.Task] = {}
        self._statuses: dict[str, str] = {}

    def submit(
        self,
        correlation_id: str,
        payload: RunRequest,
        runner: Callable[[], Awaitable[object]] | None = None,
    ) -> None:
        if runner is None:
            raise ValueError("In-memory dispatcher requires a runner callback.")
        self._statuses[correlation_id] = "queued"
        task = asyncio.create_task(self._run(correlation_id, runner))
        self._tasks[correlation_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(correlation_id, None))

    async def _run(self, correlation_id: str, runner: Callable[[], Awaitable[object]]) -> None:
        self._statuses[correlation_id] = "running"
        try:
            async with self._semaphore:
                await runner()
        except Exception:
            self._statuses[correlation_id] = "failed"
            raise
        else:
            self._statuses[correlation_id] = "completed"

    def get_status(self, correlation_id: str) -> str | None:
        return self._statuses.get(correlation_id)

    def snapshot(self) -> dict[str, Any]:
        active = sum(1 for task in self._tasks.values() if not task.done())
        return {
            "backend": self.backend_name,
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "active_jobs": active,
            "available_slots": max(self.max_concurrent_jobs - active, 0),
        }

    def healthcheck(self) -> bool:
        return True


class RedisExecutionDispatcher:
    backend_name = "redis"

    def __init__(self, redis_url: str, queue_name: str, client=None):
        self.redis_url = redis_url
        self.queue_name = queue_name
        if client is None:
            from redis import Redis

            client = Redis.from_url(redis_url, decode_responses=True)
        self.client = client

    def submit(
        self,
        correlation_id: str,
        payload: RunRequest,
        runner: Callable[[], Awaitable[object]] | None = None,
    ) -> None:
        job = AsyncExecutionJob(correlation_id=correlation_id, payload=payload.model_dump(mode="json"))
        pipeline = self.client.pipeline()
        pipeline.hset(self._status_key(correlation_id), mapping={"status": "queued"})
        pipeline.lpush(self.queue_name, job.model_dump_json())
        pipeline.execute()

    def dequeue(self, timeout_seconds: int = 5) -> AsyncExecutionJob | None:
        result = self.client.brpop(self.queue_name, timeout=timeout_seconds)
        if result is None:
            return None
        _, payload = result
        return AsyncExecutionJob.model_validate_json(payload)

    def mark_running(self, correlation_id: str) -> None:
        self.client.hset(self._status_key(correlation_id), mapping={"status": "running"})

    def mark_completed(self, correlation_id: str) -> None:
        self.client.hset(self._status_key(correlation_id), mapping={"status": "completed"})

    def mark_failed(self, correlation_id: str) -> None:
        self.client.hset(self._status_key(correlation_id), mapping={"status": "failed"})

    def get_status(self, correlation_id: str) -> str | None:
        status = self.client.hget(self._status_key(correlation_id), "status")
        return str(status) if status else None

    def snapshot(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "queue_name": self.queue_name,
            "queue_depth": int(self.client.llen(self.queue_name)),
        }

    def healthcheck(self) -> bool:
        return bool(self.client.ping())

    def _status_key(self, correlation_id: str) -> str:
        return f"coreflow:status:{correlation_id}"
