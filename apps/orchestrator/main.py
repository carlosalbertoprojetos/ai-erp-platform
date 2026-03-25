from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import time
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from application.auth import decode_jwt, issue_jwt
from application.cache import TTLCacheStore
from application.dispatcher import InMemoryExecutionDispatcher, RedisExecutionDispatcher
from application.resilience import CircuitBreaker, CircuitBreakerOpenError, retry_sync
from application.security import RateLimiter, RedisRateLimiter, configure_structured_logging, sanitize_text
from application.settings import CoreFlowSettings
from application.telemetry import MetricsRegistry
from application.tracing import TracerAdapter
from apps.orchestrator.control_plane.router import build_control_plane_router
from apps.orchestrator.iam.router import build_iam_router
from apps.orchestrator.orchestrator.registry import build_orchestrator
from domain.control_plane_models import AuthSession
from domain.iam_models import UserRecord
from domain.models import ExecutionContext, ExecutionStatusResponse, ExecutionSummary, RunRequest
from infrastructure.control_plane.repository import ControlPlaneRepository
from infrastructure.database.repository import ExecutionRepository
from infrastructure.iam.repository import IamRepository

configure_structured_logging()

app = FastAPI(title='CoreFlow Agents', version='0.3.0')
logger = logging.getLogger('coreflow.api')
submission_breaker = CircuitBreaker('execution-submit', failure_threshold=4, recovery_timeout_seconds=15)


@lru_cache
def get_settings() -> CoreFlowSettings:
    return CoreFlowSettings.from_env()


@lru_cache
def get_dispatcher() -> InMemoryExecutionDispatcher | RedisExecutionDispatcher:
    settings = get_settings()
    if settings.async_backend == 'redis':
        return RedisExecutionDispatcher(settings.redis_url, settings.redis_queue_name)
    return InMemoryExecutionDispatcher(max_concurrent_jobs=settings.max_concurrent_jobs)


@lru_cache
def get_repository() -> ExecutionRepository:
    return ExecutionRepository(get_settings().database_url)


@lru_cache
def get_control_plane_repository() -> ControlPlaneRepository:
    repository = ControlPlaneRepository(
        get_settings().database_url,
        cache_ttl_seconds=get_settings().cache_ttl_seconds,
    )
    repository.ensure_schema()
    return repository


@lru_cache
def get_iam_repository() -> IamRepository:
    settings = get_settings()
    repository = IamRepository(settings.database_url)
    repository.ensure_schema()
    repository.seed_defaults(
        tenant_name=settings.seed_tenant_name,
        plan=settings.seed_tenant_plan,
        status=settings.seed_tenant_status,
        admin_name=settings.admin_name,
        admin_email=settings.admin_email,
        admin_password=settings.admin_password,
    )
    return repository


@lru_cache
def get_rate_limiter() -> RateLimiter:
    settings = get_settings()
    fallback = RateLimiter()
    if not settings.distributed_rate_limit_enabled:
        return fallback
    try:
        from redis import Redis

        return RedisRateLimiter(
            Redis.from_url(settings.redis_url, decode_responses=True),
            prefix=settings.distributed_rate_limit_prefix,
            fallback=fallback,
        )
    except Exception:
        logger.warning('Distributed rate limiter unavailable, falling back to memory.')
        return fallback


@lru_cache
def get_metrics_registry() -> MetricsRegistry:
    return MetricsRegistry()


@lru_cache
def get_runtime_cache() -> TTLCacheStore:
    return TTLCacheStore(default_ttl_seconds=get_settings().cache_ttl_seconds)


@lru_cache
def get_tracer() -> TracerAdapter:
    settings = get_settings()
    return TracerAdapter(service_name=settings.tracing_service_name, enabled=settings.tracing_enabled)


def build_auth_session(
    username: str,
    access_token: str,
    expires_at_epoch: int,
    user_id: str | None = None,
    tenant_id: str | None = None,
    roles: list[str] | None = None,
    modules: list[str] | None = None,
) -> AuthSession:
    from datetime import datetime, timezone

    return AuthSession(
        username=username,
        access_token=access_token,
        expires_at=datetime.fromtimestamp(expires_at_epoch, tz=timezone.utc),
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles or [],
        modules=modules or [],
        scope=(roles or ['platform_admin'])[0],
    )


def issue_access_token(settings: CoreFlowSettings, user: UserRecord) -> AuthSession:
    token, expires_at = issue_jwt(settings, user)
    return build_auth_session(
        username=user.email,
        access_token=token,
        expires_at_epoch=int(expires_at.timestamp()),
        user_id=user.id,
        tenant_id=user.tenant_id,
        roles=user.roles,
        modules=user.modules,
    )


def verify_access_token(token: str, settings: CoreFlowSettings) -> AuthSession | None:
    if token == settings.api_token:
        return build_auth_session(
            username=settings.admin_username,
            access_token=token,
            expires_at_epoch=int(time.time()) + settings.auth_token_ttl_seconds,
            roles=['admin'],
            modules=['products', 'crm', 'sales', 'finance'],
        )
    principal = decode_jwt(token, settings)
    if principal is None:
        return None
    return build_auth_session(
        username=principal.email or principal.name or principal.user_id,
        access_token=token,
        expires_at_epoch=int(principal.exp.timestamp()),
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        roles=principal.roles,
        modules=principal.modules,
    )


async def require_api_token(
    request: Request,
    authorization: str | None = Header(default=None),
    settings: CoreFlowSettings = Depends(get_settings),
) -> str:
    if not settings.enforce_auth:
        return settings.admin_username
    if authorization is None or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Missing or invalid bearer token.')
    token = authorization.removeprefix('Bearer ').strip()
    principal = decode_jwt(token, settings)
    if principal is not None:
        request.state.auth_principal = principal
        return principal.email or principal.name or principal.user_id
    session = verify_access_token(token, settings)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Missing or invalid bearer token.')
    return session.username


@app.middleware('http')
async def request_logging_middleware(request: Request, call_next):
    settings = get_settings()
    limiter = get_rate_limiter()
    metrics = get_metrics_registry()
    tracer = get_tracer()
    request_id = sanitize_text(request.headers.get('x-request-id', str(uuid4())), 80)
    incoming_traceparent = request.headers.get('traceparent')
    trace_handle = tracer.start_span(f'{request.method} {request.url.path}', incoming_traceparent=incoming_traceparent)
    trace_id = trace_handle.context.trace_id
    span_id = trace_handle.context.span_id
    client_host = request.client.host if request.client else 'unknown'
    rate_key = f'{client_host}:{request.url.path}'
    limit = settings.login_rate_limit_requests if request.url.path.endswith('/auth/login') else settings.rate_limit_requests
    window = settings.login_rate_limit_window_seconds if request.url.path.endswith('/auth/login') else settings.rate_limit_window_seconds
    allowed, retry_after = limiter.check(rate_key, limit, window)
    if not allowed:
        metrics.increment('http.rate_limited')
        payload = {'detail': 'Rate limit exceeded.', 'request_id': request_id, 'retry_after': retry_after}
        response = JSONResponse(status_code=429, content=payload)
        response.headers['retry-after'] = str(retry_after)
        response.headers['x-request-id'] = request_id
        response.headers['x-trace-id'] = trace_id
        response.headers['x-span-id'] = span_id
        response.headers['traceparent'] = trace_handle.context.traceparent
        response.headers['x-content-type-options'] = 'nosniff'
        response.headers['x-frame-options'] = 'DENY'
        response.headers['referrer-policy'] = 'no-referrer'
        response.headers['cache-control'] = 'no-store'
        return response
    request.state.request_id = request_id
    request.state.trace_id = trace_id
    request.state.span_id = span_id
    request.state.traceparent = trace_handle.context.traceparent
    started = time.perf_counter()
    metrics.increment('http.requests')
    try:
        with trace_handle:
            response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        metrics.increment('http.errors')
        metrics.observe('http.duration_ms', duration_ms)
        trace_handle.set_attribute('http.method', request.method)
        trace_handle.set_attribute('http.route', request.url.path)
        logger.exception(
            'Unhandled request failure',
            extra={
                'request_id': request_id,
                'trace_id': trace_id,
                'span_id': span_id,
                'path': request.url.path,
                'method': request.method,
            },
        )
        return JSONResponse(status_code=500, content={'detail': 'Internal server error.', 'request_id': request_id})
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    metrics.observe('http.duration_ms', duration_ms)
    metrics.increment(f'http.status.{response.status_code}')
    trace_handle.set_attribute('http.method', request.method)
    trace_handle.set_attribute('http.route', request.url.path)
    trace_handle.set_attribute('http.status_code', response.status_code)
    trace_handle.set_attribute('http.duration_ms', duration_ms)
    response.headers['x-request-id'] = request_id
    response.headers['x-trace-id'] = trace_id
    response.headers['x-span-id'] = span_id
    response.headers['traceparent'] = trace_handle.context.traceparent
    response.headers['x-content-type-options'] = 'nosniff'
    response.headers['x-frame-options'] = 'DENY'
    response.headers['referrer-policy'] = 'no-referrer'
    response.headers['cache-control'] = 'no-store'
    response.headers['content-security-policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self';"
    logger.info(
        'Request completed',
        extra={
            'request_id': request_id,
            'trace_id': trace_id,
            'span_id': span_id,
            'path': request.url.path,
            'method': request.method,
            'status_code': response.status_code,
            'duration_ms': duration_ms,
            'traceparent': trace_handle.context.traceparent,
        },
    )
    return response


@app.middleware('http')
async def auth_context_middleware(request: Request, call_next):
    request.state.auth_principal = None
    authorization = request.headers.get('authorization')
    if authorization and authorization.startswith('Bearer '):
        request.state.auth_principal = decode_jwt(authorization.removeprefix('Bearer ').strip(), get_settings())
    return await call_next(request)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    request_id = getattr(request.state, 'request_id', str(uuid4()))
    logger.warning('Validation error', extra={'request_id': request_id, 'detail': str(exc)})
    return JSONResponse(status_code=400, content={'detail': str(exc), 'request_id': request_id})


@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError):
    request_id = getattr(request.state, 'request_id', str(uuid4()))
    logger.warning('Permission error', extra={'request_id': request_id, 'detail': str(exc)})
    return JSONResponse(status_code=403, content={'detail': str(exc), 'request_id': request_id})


@app.exception_handler(CircuitBreakerOpenError)
async def breaker_error_handler(request: Request, exc: CircuitBreakerOpenError):
    request_id = getattr(request.state, 'request_id', str(uuid4()))
    logger.warning('Circuit breaker open', extra={'request_id': request_id, 'detail': str(exc)})
    return JSONResponse(status_code=503, content={'detail': str(exc), 'request_id': request_id})


app.include_router(build_iam_router(get_iam_repository, get_settings))
app.include_router(build_control_plane_router(get_control_plane_repository, get_dispatcher, get_iam_repository, get_settings, require_api_token, issue_access_token, verify_access_token))

_admin_ui_path = Path(__file__).resolve().parents[1] / 'control_plane_ui'
if _admin_ui_path.exists():
    app.mount('/admin', StaticFiles(directory=str(_admin_ui_path), html=True), name='control-plane-ui')


@app.get('/health')
async def healthcheck() -> dict[str, str]:
    return {'status': 'ok'}


@app.get('/ready')
async def readiness(settings: CoreFlowSettings = Depends(get_settings)) -> dict:
    repository = get_repository()
    control_plane_repository = get_control_plane_repository()
    iam_repository = get_iam_repository()
    dispatcher = get_dispatcher()
    await asyncio.to_thread(repository.ensure_schema)
    db_ok = await asyncio.to_thread(repository.healthcheck)
    control_plane_ok = await asyncio.to_thread(control_plane_repository.healthcheck)
    iam_ok = await asyncio.to_thread(iam_repository.healthcheck)
    queue_ok = dispatcher.healthcheck() if isinstance(dispatcher, InMemoryExecutionDispatcher) else await asyncio.to_thread(dispatcher.healthcheck)
    overall = 'ok' if db_ok and queue_ok and control_plane_ok and iam_ok else 'degraded'
    return {
        'status': overall,
        'database': 'ok' if db_ok else 'unavailable',
        'control_plane': 'ok' if control_plane_ok else 'unavailable',
        'iam': 'ok' if iam_ok else 'unavailable',
        'queue': 'ok' if queue_ok else 'unavailable',
        'dispatcher': dispatcher.snapshot(),
        'auth_enforced': settings.enforce_auth,
        'default_provider': settings.default_provider,
        'async_backend': settings.async_backend,
        'admin_ui': '/admin/',
    }


@app.get('/metrics')
async def metrics(_: str = Depends(require_api_token)) -> dict:
    return get_metrics_registry().snapshot()


@app.get('/metrics/prometheus')
async def metrics_prometheus(_: str = Depends(require_api_token)) -> PlainTextResponse:
    return PlainTextResponse(
        get_metrics_registry().to_prometheus(get_settings().prometheus_namespace),
        media_type='text/plain; version=0.0.4; charset=utf-8',
    )


@app.post('/run', response_model=ExecutionSummary)
async def run(payload: RunRequest, _: str = Depends(require_api_token)) -> ExecutionSummary:
    settings = get_settings()
    provider = payload.provider or settings.default_provider
    orchestrator = build_orchestrator(provider_name=provider, settings=settings)
    return await orchestrator.run(payload.model_copy(update={'provider': provider}))


@app.post('/run/async', response_model=ExecutionStatusResponse)
async def run_async(payload: RunRequest, _: str = Depends(require_api_token)) -> ExecutionStatusResponse:
    settings = get_settings()
    repository = get_repository()
    dispatcher = get_dispatcher()
    runtime_cache = get_runtime_cache()
    correlation_id = payload.correlation_id or ExecutionContext(request=payload.request, target_root=payload.target_root).correlation_id
    provider = payload.provider or settings.default_provider
    queued_payload = payload.model_copy(update={'correlation_id': correlation_id, 'provider': provider})
    queued_context = ExecutionContext(correlation_id=correlation_id, request=queued_payload.request, target_root=queued_payload.target_root, dry_run=queued_payload.dry_run, git=queued_payload.git)
    await asyncio.to_thread(repository.ensure_schema)
    await asyncio.to_thread(repository.create_execution, queued_context, queued_payload.pipeline_name, 'queued')
    runner = lambda: build_orchestrator(provider_name=provider, settings=settings).run(queued_payload)
    submission_key = f'execution-status:{correlation_id}'
    runtime_cache.set(submission_key, {'status': 'queued'})
    if isinstance(dispatcher, InMemoryExecutionDispatcher):
        submission_breaker.execute(lambda: retry_sync(lambda: dispatcher.submit(correlation_id, queued_payload, runner), attempts=2, backoff_seconds=0.1))
    else:
        await asyncio.to_thread(submission_breaker.execute, lambda: retry_sync(lambda: dispatcher.submit(correlation_id, queued_payload, runner), attempts=2, backoff_seconds=0.1))
    return ExecutionStatusResponse(correlation_id=correlation_id, status='queued')


@app.get('/executions/{correlation_id}', response_model=ExecutionStatusResponse)
async def get_execution_status(correlation_id: str, _: str = Depends(require_api_token)) -> ExecutionStatusResponse:
    dispatcher = get_dispatcher()
    runtime_cache = get_runtime_cache()
    status_response = await asyncio.to_thread(get_repository().get_execution_status, correlation_id)
    local_status = dispatcher.get_status(correlation_id) if isinstance(dispatcher, InMemoryExecutionDispatcher) else await asyncio.to_thread(dispatcher.get_status, correlation_id)
    if status_response is not None:
        if local_status in {'running', 'failed', 'completed'} and status_response.status == 'queued':
            return status_response.model_copy(update={'status': local_status})
        return status_response
    cached_status = runtime_cache.get(f'execution-status:{correlation_id}')
    if cached_status is not None:
        return ExecutionStatusResponse(correlation_id=correlation_id, status=str(cached_status['status']))
    if local_status is not None:
        return ExecutionStatusResponse(correlation_id=correlation_id, status=local_status)
    raise HTTPException(status_code=404, detail='Execution not found.')



