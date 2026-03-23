from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from application.resilience import CircuitBreaker, retry_sync
from application.security import sanitize_email, sanitize_metadata, sanitize_slug, sanitize_text
from application.settings import CoreFlowSettings
from domain.control_plane_models import (
    AuditLogRecord,
    AuthSession,
    BillingOverview,
    DashboardSummary,
    ModuleFlagRecord,
    PaginatedResponse,
    PlanRecord,
    RoleRecord,
    SystemHealthSummary,
    TenantDetail,
    TenantRecord,
    TenantUserRecord,
)
from infrastructure.control_plane.repository import ControlPlaneRepository

logger = logging.getLogger('coreflow.control_plane')
write_breaker = CircuitBreaker('control-plane-write', failure_threshold=3, recovery_timeout_seconds=20)


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator('username', 'password')
    @classmethod
    def sanitize_credentials(cls, value: str) -> str:
        return sanitize_text(value, 120)


class ClientLogRequest(BaseModel):
    level: str = 'info'
    message: str
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator('message')
    @classmethod
    def sanitize_message(cls, value: str) -> str:
        return sanitize_text(value, 240)


class RoleUpsertRequest(BaseModel):
    id: str | None = None
    name: str
    scope: str
    permissions: list[str] = Field(default_factory=list)

    @field_validator('name', 'scope')
    @classmethod
    def sanitize_basic_fields(cls, value: str) -> str:
        return sanitize_text(value, 120)


class UserRoleUpdateRequest(BaseModel):
    role: str

    @field_validator('role')
    @classmethod
    def sanitize_role(cls, value: str) -> str:
        return sanitize_text(value, 120)


class ModuleFlagUpdateRequest(BaseModel):
    enabled: bool
    rollout: int = Field(default=100, ge=0, le=100)


class TenantCreateRequest(BaseModel):
    name: str
    slug: str
    region: str = 'us-east-1'
    plan_key: str
    billing_email: str
    timezone: str = 'UTC'
    locale: str = 'en-US'
    enforce_sso: bool = False

    @field_validator('name', 'region', 'plan_key', 'timezone', 'locale')
    @classmethod
    def sanitize_fields(cls, value: str) -> str:
        return sanitize_text(value, 120)

    @field_validator('slug')
    @classmethod
    def sanitize_slug_field(cls, value: str) -> str:
        return sanitize_slug(value)

    @field_validator('billing_email')
    @classmethod
    def sanitize_billing_email(cls, value: str) -> str:
        return sanitize_email(value)


class TenantPlanAssignRequest(BaseModel):
    plan_key: str
    status: str = 'active'

    @field_validator('plan_key', 'status')
    @classmethod
    def sanitize_plan_fields(cls, value: str) -> str:
        return sanitize_text(value, 120)


class SessionEnvelope(BaseModel):
    authenticated: bool
    session: AuthSession | None = None


SessionIssuer = Callable[[CoreFlowSettings, str], AuthSession]
SessionVerifier = Callable[[str, CoreFlowSettings], AuthSession | None]


def build_control_plane_router(
    get_repository: Callable[[], ControlPlaneRepository],
    get_dispatcher: Callable[[], Any],
    get_settings: Callable[[], CoreFlowSettings],
    require_api_token: Callable[..., Any],
    issue_access_token: SessionIssuer,
    verify_access_token: SessionVerifier,
) -> APIRouter:
    router = APIRouter(prefix='/api/control-plane', tags=['control-plane'])

    def request_context(request: Request) -> tuple[str | None, str | None]:
        return getattr(request.state, 'request_id', None), getattr(request.state, 'trace_id', None)

    def scoped_tenant(x_tenant_id: str | None) -> str | None:
        return sanitize_text(x_tenant_id, 80) if x_tenant_id else None

    @router.post('/auth/login', response_model=AuthSession)
    async def login(payload: LoginRequest, request: Request) -> AuthSession:
        settings = get_settings()
        repository = get_repository()
        request_id, trace_id = request_context(request)
        if payload.username != settings.admin_username or payload.password != settings.admin_password:
            await asyncio.to_thread(repository.record_audit_log, payload.username, 'auth.login', 'session', None, None, 'denied', request_id, trace_id, {'reason': 'invalid_credentials'})
            raise HTTPException(status_code=401, detail='Invalid username or password.')
        session = issue_access_token(settings, payload.username)
        await asyncio.to_thread(repository.record_audit_log, payload.username, 'auth.login', 'session', None, None, 'success', request_id, trace_id, {})
        return session

    @router.get('/auth/session', response_model=SessionEnvelope)
    async def session_status(request: Request, _: str = Depends(require_api_token), authorization: str | None = Header(default=None)) -> SessionEnvelope:
        settings = get_settings()
        token = (authorization or '').removeprefix('Bearer ').strip()
        session = verify_access_token(token, settings)
        if session is None:
            raise HTTPException(status_code=401, detail='Session is not valid.')
        return SessionEnvelope(authenticated=True, session=session)

    @router.post('/client-logs')
    async def client_logs(payload: ClientLogRequest, _: str = Depends(require_api_token)) -> dict[str, str]:
        logger.log(getattr(logging, payload.level.upper(), logging.INFO), payload.message, extra={'client_context': sanitize_metadata(payload.context)})
        return {'status': 'recorded'}

    @router.get('/dashboard', response_model=DashboardSummary)
    async def dashboard(_: str = Depends(require_api_token)) -> DashboardSummary:
        return await asyncio.to_thread(get_repository().get_dashboard_summary)

    @router.get('/plans', response_model=list[PlanRecord])
    async def plans(_: str = Depends(require_api_token)) -> list[PlanRecord]:
        return await asyncio.to_thread(get_repository().list_plans)

    @router.get('/tenants', response_model=PaginatedResponse[TenantRecord])
    async def list_tenants(search: str | None = None, status: str | None = None, limit: int = 25, offset: int = 0, _: str = Depends(require_api_token)) -> PaginatedResponse[TenantRecord]:
        items, total = await asyncio.to_thread(get_repository().list_tenants, search, status, limit, offset)
        return PaginatedResponse[TenantRecord](items=items, total=total, limit=limit, offset=offset)

    @router.post('/tenants', response_model=TenantDetail)
    async def create_tenant(payload: TenantCreateRequest, request: Request, _: str = Depends(require_api_token), idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')) -> TenantDetail:
        repository = get_repository()
        request_id, trace_id = request_context(request)
        result = await asyncio.to_thread(
            write_breaker.execute,
            lambda: retry_sync(lambda: repository.create_tenant(payload.name, payload.slug, payload.region, payload.plan_key, payload.billing_email, payload.timezone, payload.locale, payload.enforce_sso, idempotency_key=idempotency_key, actor=_, request_id=request_id, trace_id=trace_id), attempts=2),
        )
        return result

    @router.get('/tenants/{tenant_id}', response_model=TenantDetail)
    async def tenant_detail(tenant_id: str, _: str = Depends(require_api_token), x_tenant_id: str | None = Header(default=None, alias='X-Tenant-Id')) -> TenantDetail:
        detail = await asyncio.to_thread(get_repository().get_tenant_detail, tenant_id, scoped_tenant(x_tenant_id))
        if detail is None:
            raise HTTPException(status_code=404, detail='Tenant not found.')
        return detail

    @router.patch('/tenants/{tenant_id}/plan', response_model=TenantDetail)
    async def assign_plan(tenant_id: str, payload: TenantPlanAssignRequest, request: Request, _: str = Depends(require_api_token), idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'), x_tenant_id: str | None = Header(default=None, alias='X-Tenant-Id')) -> TenantDetail:
        repository = get_repository()
        request_id, trace_id = request_context(request)
        detail = await asyncio.to_thread(
            write_breaker.execute,
            lambda: retry_sync(lambda: repository.assign_plan(tenant_id, payload.plan_key, payload.status, idempotency_key=idempotency_key, actor=_, request_id=request_id, trace_id=trace_id, scoped_tenant_id=scoped_tenant(x_tenant_id)), attempts=2),
        )
        if detail is None:
            raise HTTPException(status_code=404, detail='Tenant not found.')
        return detail

    @router.get('/billing', response_model=BillingOverview)
    async def billing(status: str | None = None, limit: int = 50, offset: int = 0, _: str = Depends(require_api_token)) -> BillingOverview:
        return await asyncio.to_thread(get_repository().get_billing_overview, status, limit, offset)

    @router.get('/system-health', response_model=SystemHealthSummary)
    async def system_health(_: str = Depends(require_api_token)) -> SystemHealthSummary:
        repository = get_repository()
        dispatcher = get_dispatcher()
        database_ok = await asyncio.to_thread(repository.healthcheck)
        queue_ok = dispatcher.healthcheck() if hasattr(dispatcher, 'healthcheck') else True
        snapshot = dispatcher.snapshot() if hasattr(dispatcher, 'snapshot') else {}
        return await asyncio.to_thread(repository.get_system_health, int(snapshot.get('queue_depth', 0)), int(snapshot.get('active_jobs', 0)), database_ok, queue_ok)

    @router.get('/audit-logs', response_model=PaginatedResponse[AuditLogRecord])
    async def audit_logs(limit: int = 50, offset: int = 0, _: str = Depends(require_api_token), x_tenant_id: str | None = Header(default=None, alias='X-Tenant-Id')) -> PaginatedResponse[AuditLogRecord]:
        items, total = await asyncio.to_thread(get_repository().list_audit_logs, scoped_tenant(x_tenant_id), limit, offset)
        return PaginatedResponse[AuditLogRecord](items=items, total=total, limit=limit, offset=offset)

    @router.get('/users', response_model=PaginatedResponse[TenantUserRecord])
    async def list_users(search: str | None = None, role: str | None = None, limit: int = 25, offset: int = 0, _: str = Depends(require_api_token), x_tenant_id: str | None = Header(default=None, alias='X-Tenant-Id')) -> PaginatedResponse[TenantUserRecord]:
        items, total = await asyncio.to_thread(get_repository().list_users, search, role, scoped_tenant(x_tenant_id), limit, offset)
        return PaginatedResponse[TenantUserRecord](items=items, total=total, limit=limit, offset=offset)

    @router.get('/roles', response_model=list[RoleRecord])
    async def list_roles(_: str = Depends(require_api_token)) -> list[RoleRecord]:
        return await asyncio.to_thread(get_repository().list_roles)

    @router.put('/roles', response_model=RoleRecord)
    async def upsert_role(payload: RoleUpsertRequest, request: Request, _: str = Depends(require_api_token)) -> RoleRecord:
        repository = get_repository()
        request_id, trace_id = request_context(request)
        return await asyncio.to_thread(write_breaker.execute, lambda: retry_sync(lambda: repository.upsert_role(payload.id, payload.name, payload.scope, payload.permissions, actor=_, request_id=request_id, trace_id=trace_id), attempts=2))

    @router.patch('/users/{user_id}/role', response_model=TenantUserRecord)
    async def update_user_role(user_id: str, payload: UserRoleUpdateRequest, request: Request, _: str = Depends(require_api_token), x_tenant_id: str | None = Header(default=None, alias='X-Tenant-Id')) -> TenantUserRecord:
        repository = get_repository()
        request_id, trace_id = request_context(request)
        record = await asyncio.to_thread(write_breaker.execute, lambda: retry_sync(lambda: repository.update_user_role(user_id, payload.role, scoped_tenant(x_tenant_id), actor=_, request_id=request_id, trace_id=trace_id), attempts=2))
        if record is None:
            raise HTTPException(status_code=404, detail='User not found.')
        return record

    @router.get('/modules', response_model=PaginatedResponse[ModuleFlagRecord])
    async def list_modules(limit: int = 50, offset: int = 0, tenant_id: str | None = None, _: str = Depends(require_api_token), x_tenant_id: str | None = Header(default=None, alias='X-Tenant-Id')) -> PaginatedResponse[ModuleFlagRecord]:
        scoped = scoped_tenant(x_tenant_id) or scoped_tenant(tenant_id)
        items, total = await asyncio.to_thread(get_repository().list_modules, scoped, limit, offset)
        return PaginatedResponse[ModuleFlagRecord](items=items, total=total, limit=limit, offset=offset)

    @router.patch('/modules/{module_id}', response_model=ModuleFlagRecord)
    async def update_module(module_id: str, payload: ModuleFlagUpdateRequest, request: Request, _: str = Depends(require_api_token), x_tenant_id: str | None = Header(default=None, alias='X-Tenant-Id')) -> ModuleFlagRecord:
        repository = get_repository()
        request_id, trace_id = request_context(request)
        record = await asyncio.to_thread(write_breaker.execute, lambda: retry_sync(lambda: repository.update_module_flag(module_id, payload.enabled, payload.rollout, scoped_tenant(x_tenant_id), actor=_, request_id=request_id, trace_id=trace_id), attempts=2))
        if record is None:
            raise HTTPException(status_code=404, detail='Module flag not found.')
        return record

    return router
