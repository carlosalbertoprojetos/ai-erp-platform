from __future__ import annotations

import asyncio
import logging

from application.dispatcher import RedisExecutionDispatcher
from application.settings import CoreFlowSettings
from apps.orchestrator.orchestrator.registry import build_orchestrator
from domain.models import RunRequest


async def run_worker() -> None:
    settings = CoreFlowSettings.from_env()
    if settings.async_backend != "redis":
        raise RuntimeError("Worker requires COREFLOW_ASYNC_BACKEND=redis.")

    dispatcher = RedisExecutionDispatcher(settings.redis_url, settings.redis_queue_name)
    repository = build_orchestrator(provider_name=settings.default_provider, settings=settings).execution_repository
    await asyncio.to_thread(repository.ensure_schema)

    while True:
        job = await asyncio.to_thread(dispatcher.dequeue, settings.worker_poll_timeout_seconds)
        if job is None:
            await asyncio.sleep(0.1)
            continue

        request = RunRequest.model_validate(job.payload)
        await asyncio.to_thread(dispatcher.mark_running, job.correlation_id)
        try:
            orchestrator = build_orchestrator(provider_name=request.provider, settings=settings)
            await orchestrator.run(request)
        except Exception:
            logging.exception("Worker failed to process job %s", job.correlation_id)
            await asyncio.to_thread(dispatcher.mark_failed, job.correlation_id)
        else:
            await asyncio.to_thread(dispatcher.mark_completed, job.correlation_id)


if __name__ == "__main__":
    asyncio.run(run_worker())
