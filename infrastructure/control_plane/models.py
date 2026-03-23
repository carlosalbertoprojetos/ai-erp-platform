from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.models import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantControlPlaneModel(Base):
    __tablename__ = 'cp_tenants'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(200), unique=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    region: Mapped[str] = mapped_column(String(64), default='us-east-1')
    plan: Mapped[str] = mapped_column(String(64), default='growth')
    status: Mapped[str] = mapped_column(String(32), default='active')
    monthly_recurring_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    settings_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    usage_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    users: Mapped[list['TenantUserModel']] = relationship(back_populates='tenant', cascade='all, delete-orphan')
    subscriptions: Mapped[list['SubscriptionModel']] = relationship(back_populates='tenant', cascade='all, delete-orphan')
    invoices: Mapped[list['InvoiceModel']] = relationship(back_populates='tenant', cascade='all, delete-orphan')
    modules: Mapped[list['ModuleFlagModel']] = relationship(back_populates='tenant', cascade='all, delete-orphan')


class TenantUserModel(Base):
    __tablename__ = 'cp_tenant_users'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey('cp_tenants.id'), index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), index=True)
    role: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default='active')
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped[TenantControlPlaneModel] = relationship(back_populates='users')


class SubscriptionModel(Base):
    __tablename__ = 'cp_subscriptions'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey('cp_tenants.id'), index=True)
    plan: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default='active')
    amount_monthly: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(12), default='USD')
    billing_cycle: Mapped[str] = mapped_column(String(32), default='monthly')
    renewal_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped[TenantControlPlaneModel] = relationship(back_populates='subscriptions')


class InvoiceModel(Base):
    __tablename__ = 'cp_invoices'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey('cp_tenants.id'), index=True)
    number: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(32), default='open')
    total: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(12), default='USD')
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    tenant: Mapped[TenantControlPlaneModel] = relationship(back_populates='invoices')


class RoleModel(Base):
    __tablename__ = 'cp_roles'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(100), unique=True)
    scope: Mapped[str] = mapped_column(String(32), default='tenant')
    permissions_payload: Mapped[list[str]] = mapped_column(JSON, default=list)


class PlanModel(Base):
    __tablename__ = 'cp_plans'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(12), default='USD')
    monthly_price: Mapped[float] = mapped_column(Float, default=0.0)
    included_modules: Mapped[list[str]] = mapped_column(JSON, default=list)
    max_users: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(32), default='active')


class ModuleFlagModel(Base):
    __tablename__ = 'cp_module_flags'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey('cp_tenants.id'), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(100), index=True)
    label: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rollout: Mapped[int] = mapped_column(Integer, default=100)

    tenant: Mapped[TenantControlPlaneModel | None] = relationship(back_populates='modules')


class BillingEventModel(Base):
    __tablename__ = 'cp_billing_events'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default='applied')
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditLogModel(Base):
    __tablename__ = 'cp_audit_logs'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default='success')
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SystemAlertModel(Base):
    __tablename__ = 'cp_system_alerts'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    severity: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
