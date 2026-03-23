from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field


T = TypeVar('T')


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


TenantStatus = Literal['active', 'trialing', 'suspended', 'churn_risk']
SubscriptionStatus = Literal['trialing', 'active', 'past_due', 'cancelled']
InvoiceStatus = Literal['paid', 'open', 'past_due', 'void']
SystemHealthStatus = Literal['healthy', 'degraded', 'critical']


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


class TenantRecord(BaseModel):
    id: str
    name: str
    slug: str
    region: str
    plan: str
    status: TenantStatus
    monthly_recurring_revenue: float = 0.0
    active_users: int = 0
    created_at: datetime = Field(default_factory=utc_now)


class TenantUsageSummary(BaseModel):
    api_requests_24h: int = 0
    workflow_runs_24h: int = 0
    storage_gb: float = 0.0
    error_rate_percent: float = 0.0


class TenantSettingsRecord(BaseModel):
    timezone: str = 'UTC'
    locale: str = 'en-US'
    billing_email: str = ''
    enforce_sso: bool = False


class TenantUserRecord(BaseModel):
    id: str
    tenant_id: str
    full_name: str
    email: str
    role: str
    status: str
    last_active_at: datetime | None = None


class SubscriptionRecord(BaseModel):
    id: str
    tenant_id: str
    plan: str
    status: SubscriptionStatus
    amount_monthly: float
    currency: str = 'USD'
    billing_cycle: str = 'monthly'
    renewal_date: datetime | None = None


class InvoiceRecord(BaseModel):
    id: str
    tenant_id: str
    number: str
    status: InvoiceStatus
    total: float
    currency: str = 'USD'
    due_date: datetime | None = None
    issued_at: datetime = Field(default_factory=utc_now)


class RoleRecord(BaseModel):
    id: str
    name: str
    scope: str
    permissions: list[str] = Field(default_factory=list)


class ModuleFlagRecord(BaseModel):
    id: str
    tenant_id: str | None = None
    key: str
    label: str
    category: str
    enabled: bool = False
    rollout: int = 100


class PlanRecord(BaseModel):
    id: str
    key: str
    label: str
    currency: str = 'USD'
    monthly_price: float
    included_modules: list[str] = Field(default_factory=list)
    max_users: int
    status: str = 'active'


class AuditLogRecord(BaseModel):
    id: str
    actor: str
    action: str
    entity_type: str
    entity_id: str | None = None
    tenant_id: str | None = None
    status: str = 'success'
    request_id: str | None = None
    trace_id: str | None = None
    payload: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class MetricPoint(BaseModel):
    label: str
    value: float
    unit: str = ''


class AlertRecord(BaseModel):
    id: str
    severity: str
    source: str
    message: str
    created_at: datetime = Field(default_factory=utc_now)


class SystemLogRecord(BaseModel):
    id: str
    level: str
    source: str
    message: str
    created_at: datetime = Field(default_factory=utc_now)


class DashboardSummary(BaseModel):
    mrr: float
    active_tenants: int
    open_errors: int
    system_health: SystemHealthStatus
    mrr_delta_percent: float = 0.0
    tenant_growth_percent: float = 0.0
    system_health_score: int = 100
    revenue_series: list[MetricPoint] = Field(default_factory=list)
    tenant_distribution: list[MetricPoint] = Field(default_factory=list)


class TenantDetail(BaseModel):
    tenant: TenantRecord
    users: list[TenantUserRecord] = Field(default_factory=list)
    subscriptions: list[SubscriptionRecord] = Field(default_factory=list)
    invoices: list[InvoiceRecord] = Field(default_factory=list)
    usage: TenantUsageSummary = Field(default_factory=TenantUsageSummary)
    settings: TenantSettingsRecord = Field(default_factory=TenantSettingsRecord)
    modules: list[ModuleFlagRecord] = Field(default_factory=list)


class SystemHealthSummary(BaseModel):
    status: SystemHealthStatus
    logs: list[SystemLogRecord] = Field(default_factory=list)
    alerts: list[AlertRecord] = Field(default_factory=list)
    metrics: list[MetricPoint] = Field(default_factory=list)


class BillingOverview(BaseModel):
    subscriptions: list[SubscriptionRecord] = Field(default_factory=list)
    invoices: list[InvoiceRecord] = Field(default_factory=list)
    monthly_volume: float = 0.0
    past_due_total: float = 0.0


class AuthSession(BaseModel):
    username: str
    scope: str = 'platform_admin'
    access_token: str
    expires_at: datetime


class ControlPlaneSeedSummary(BaseModel):
    tenants_created: int
    users_created: int
    invoices_created: int
