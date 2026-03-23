from __future__ import annotations

import asyncio

from application.dispatcher import InMemoryExecutionDispatcher, RedisExecutionDispatcher
from domain.models import RunRequest


class _FakeRedisPipeline:
    def __init__(self, client):
        self.client = client
        self.operations = []

    def hset(self, key, mapping):
        self.operations.append(("hset", key, mapping))
        return self

    def lpush(self, key, value):
        self.operations.append(("lpush", key, value))
        return self

    def execute(self):
        for operation, key, value in self.operations:
            if operation == "hset":
                self.client.hashes.setdefault(key, {}).update(value)
            elif operation == "lpush":
                self.client.queue.insert(0, value)
        return True


class _FakeRedisClient:
    def __init__(self):
        self.queue = []
        self.hashes = {}

    def pipeline(self):
        return _FakeRedisPipeline(self)

    def brpop(self, key, timeout=0):
        if not self.queue:
            return None
        return key, self.queue.pop()

    def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update(mapping)

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def llen(self, key):
        return len(self.queue)

    def ping(self):
        return True


async def test_in_memory_dispatcher_tracks_status():
    dispatcher = InMemoryExecutionDispatcher(max_concurrent_jobs=1)
    payload = RunRequest(request={"title": "A", "description": "B"}, target_root="generated")

    async def runner():
        await asyncio.sleep(0.01)

    dispatcher.submit("corr-1", payload, runner)
    assert dispatcher.get_status("corr-1") in {"queued", "running"}

    for _ in range(20):
        if dispatcher.get_status("corr-1") == "completed":
            break
        await asyncio.sleep(0.01)

    assert dispatcher.get_status("corr-1") == "completed"


def test_redis_dispatcher_enqueues_and_tracks_status():
    client = _FakeRedisClient()
    dispatcher = RedisExecutionDispatcher("redis://example", "coreflow:jobs", client=client)
    payload = RunRequest(request={"title": "A", "description": "B"}, target_root="generated", correlation_id="corr-1")

    dispatcher.submit("corr-1", payload)
    assert dispatcher.get_status("corr-1") == "queued"
    job = dispatcher.dequeue(timeout_seconds=1)
    assert job is not None
    assert job.correlation_id == "corr-1"
    dispatcher.mark_running("corr-1")
    assert dispatcher.get_status("corr-1") == "running"
    dispatcher.mark_completed("corr-1")
    assert dispatcher.get_status("corr-1") == "completed"
    assert dispatcher.healthcheck() is True
