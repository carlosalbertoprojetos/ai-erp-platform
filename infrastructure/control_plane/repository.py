from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, desc, func, select
from sqlalchemy.orm import Session, joinedload, sessionmaker

from application.cache import TTLCacheStore
from application.security import sanitize_metadata
from domain.control_plane_models import (
    AlertRecord,
    AuditLogRecord,
    BillingOverview,
    ControlPlaneSeedSummary,
    DashboardSummary,
    InvoiceRecord,
    MetricPoint,
    ModuleFlagRecord,
    PlanRecord,
    RoleRecord,
    SubscriptionRecord,
    SystemHealthSummary,
    SystemLogRecord,
    TenantDetail,
    TenantRecord,
    TenantSettingsRecord,
    TenantUsageSummary,
    TenantUserRecord,
)
from infrastructure.control_plane.models import (
    AuditLogModel,
    BillingEventModel,
    InvoiceModel,
    ModuleFlagModel,
    PlanModel,
    RoleModel,
    SubscriptionModel,
    SystemAlertModel,
    TenantControlPlaneModel,
    TenantUserModel,
)
from infrastructure.database.models import Base, ExecutionLogModel, ExecutionModel


class ControlPlaneRepository:
    def __init__(self, database_url: str = 'sqlite:///./.coreflow/coreflow.db', cache_ttl_seconds: int = 15):
        self.database_url = database_url
        if database_url.startswith('sqlite:///'):
            database_path = Path(database_url.replace('sqlite:///', '', 1))
            database_path.parent.mkdir(parents=True, exist_ok=True)
        connect_args = {'check_same_thread': False} if database_url.startswith('sqlite') else {}
        self.engine = create_engine(database_url, future=True, connect_args=connect_args, pool_pre_ping=True)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, class_=Session)
        self.cache = TTLCacheStore(default_ttl_seconds=cache_ttl_seconds)

    def ensure_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def healthcheck(self) -> bool:
        with self.engine.connect() as connection:
            connection.exec_driver_sql('SELECT 1')
        return True

    def seed_defaults(self) -> ControlPlaneSeedSummary:
        with self.session_factory() as session:
            created_tenants = 0
            created_users = 0
            created_invoices = 0
            self._seed_roles(session)
            self._seed_plans(session)
            if session.scalar(select(func.count()).select_from(TenantControlPlaneModel)) == 0:
                now = datetime.now(timezone.utc)
                tenants = [
                    self._create_seed_tenant(session, 'Northstar Logistics', 'northstar-logistics', 'us-east-1', 'enterprise', 'active', 'finance@northstar.test', 'America/New_York', True, {'api_requests_24h': 184320, 'workflow_runs_24h': 860, 'storage_gb': 248.7, 'error_rate_percent': 0.4}),
                    self._create_seed_tenant(session, 'Apex Retail Group', 'apex-retail-group', 'eu-west-1', 'growth', 'active', 'billing@apex.test', 'Europe/Dublin', False, {'api_requests_24h': 96410, 'workflow_runs_24h': 430, 'storage_gb': 96.4, 'error_rate_percent': 0.8}),
                    self._create_seed_tenant(session, 'BlueOrbit Health', 'blueorbit-health', 'ap-southeast-1', 'enterprise', 'churn_risk', 'ops@blueorbit.test', 'Asia/Singapore', True, {'api_requests_24h': 143280, 'workflow_runs_24h': 510, 'storage_gb': 172.1, 'error_rate_percent': 1.7}),
                    self._create_seed_tenant(session, 'Mercury Field Services', 'mercury-field-services', 'us-west-2', 'starter', 'trialing', 'owner@mercury.test', 'America/Los_Angeles', False, {'api_requests_24h': 18320, 'workflow_runs_24h': 74, 'storage_gb': 14.9, 'error_rate_percent': 0.3}),
                ]
                session.flush()
                created_tenants = len(tenants)
                users = [
                    TenantUserModel(tenant_id=tenants[0].id, full_name='Lena Carter', email='lena@northstar.test', role='tenant_admin', status='active', last_active_at=now - timedelta(minutes=14)),
                    TenantUserModel(tenant_id=tenants[0].id, full_name='Jon Silva', email='jon@northstar.test', role='finance_manager', status='active', last_active_at=now - timedelta(hours=2)),
                    TenantUserModel(tenant_id=tenants[1].id, full_name='Maya Brooks', email='maya@apex.test', role='tenant_admin', status='active', last_active_at=now - timedelta(minutes=52)),
                    TenantUserModel(tenant_id=tenants[1].id, full_name='Chris Hall', email='chris@apex.test', role='sales_manager', status='invited', last_active_at=None),
                    TenantUserModel(tenant_id=tenants[2].id, full_name='Ari Khan', email='ari@blueorbit.test', role='tenant_admin', status='active', last_active_at=now - timedelta(minutes=31)),
                    TenantUserModel(tenant_id=tenants[3].id, full_name='Noah Reed', email='noah@mercury.test', role='tenant_owner', status='active', last_active_at=now - timedelta(minutes=9)),
                ]
                session.add_all(users)
                created_users = len(users)
                for tenant in tenants:
                    invoice = self._ensure_subscription(session, tenant, tenant.plan, 'trialing' if tenant.status == 'trialing' else ('past_due' if tenant.status == 'churn_risk' else 'active'), issue_invoice=True)
                    if invoice is not None:
                        created_invoices += 1
                session.add_all(
                    [
                        SystemAlertModel(severity='critical', source='billing', message='1 enterprise subscription is past due and entering grace enforcement window.'),
                        SystemAlertModel(severity='warning', source='orchestrator', message='Retry rate is elevated for backend generation jobs in us-east-1.'),
                    ]
                )
            session.commit()
            self.cache.invalidate()
            return ControlPlaneSeedSummary(tenants_created=created_tenants, users_created=created_users, invoices_created=created_invoices)

    def list_plans(self) -> list[PlanRecord]:
        cache_key = 'plans'
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        with self.session_factory() as session:
            plans = session.execute(select(PlanModel).order_by(PlanModel.monthly_price)).scalars().all()
            return self.cache.set(cache_key, [self._to_plan_record(item) for item in plans])

    def list_tenants(self, search: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[TenantRecord], int]:
        cache_key = f'tenants:{search}:{status}:{limit}:{offset}'
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        with self.session_factory() as session:
            statement = select(TenantControlPlaneModel).options(joinedload(TenantControlPlaneModel.users)).order_by(TenantControlPlaneModel.name)
            tenants = session.execute(statement).unique().scalars().all()
            records = [self._to_tenant_record(item, len(item.users)) for item in tenants]
            filtered = [item for item in records if self._matches_tenant(item, search, status)]
            result = (filtered[offset: offset + limit], len(filtered))
            self.cache.set(cache_key, result)
            return result

    def list_audit_logs(self, tenant_id: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[AuditLogRecord], int]:
        with self.session_factory() as session:
            statement = select(AuditLogModel).order_by(desc(AuditLogModel.created_at))
            count_statement = select(func.count()).select_from(AuditLogModel)
            if tenant_id:
                statement = statement.where(AuditLogModel.tenant_id == tenant_id)
                count_statement = count_statement.where(AuditLogModel.tenant_id == tenant_id)
            total = session.scalar(count_statement) or 0
            rows = session.execute(statement.offset(offset).limit(limit)).scalars().all()
            return [self._to_audit_record(item) for item in rows], int(total)

    def create_tenant(self, name: str, slug: str, region: str, plan_key: str, billing_email: str, timezone_name: str, locale: str, enforce_sso: bool, idempotency_key: str | None = None, actor: str = 'system', request_id: str | None = None, trace_id: str | None = None) -> TenantDetail:
        with self.session_factory() as session:
            if idempotency_key:
                existing_event = session.execute(select(BillingEventModel).where(BillingEventModel.idempotency_key == idempotency_key)).scalar_one_or_none()
                if existing_event is not None and existing_event.result_payload.get('tenant_id'):
                    detail = self.get_tenant_detail(existing_event.result_payload['tenant_id'])
                    if detail is not None:
                        return detail
            existing = session.execute(select(TenantControlPlaneModel).where(TenantControlPlaneModel.slug == slug)).scalar_one_or_none()
            if existing is not None:
                raise ValueError('A tenant with this slug already exists.')
            tenant = self._create_seed_tenant(session, name, slug, region, plan_key, 'trialing', billing_email, timezone_name, enforce_sso, {'api_requests_24h': 0, 'workflow_runs_24h': 0, 'storage_gb': 0.0, 'error_rate_percent': 0.0}, locale=locale)
            self._ensure_subscription(session, tenant, plan_key, 'trialing', issue_invoice=True)
            if idempotency_key:
                session.add(BillingEventModel(tenant_id=tenant.id, event_type='tenant_created', idempotency_key=idempotency_key, payload={'plan_key': plan_key}, result_payload={'tenant_id': tenant.id}))
            self._record_audit(session, actor, 'tenant.create', 'tenant', tenant.id, tenant.id, 'success', request_id, trace_id, {'plan_key': plan_key, 'region': region})
            session.commit()
            self.cache.invalidate()
            detail = self.get_tenant_detail(tenant.id)
            if detail is None:
                raise ValueError('Created tenant could not be loaded.')
            return detail

    def assign_plan(self, tenant_id: str, plan_key: str, status: str = 'active', idempotency_key: str | None = None, actor: str = 'system', request_id: str | None = None, trace_id: str | None = None, scoped_tenant_id: str | None = None) -> TenantDetail | None:
        with self.session_factory() as session:
            tenant = session.execute(select(TenantControlPlaneModel).options(joinedload(TenantControlPlaneModel.modules), joinedload(TenantControlPlaneModel.subscriptions)).where(TenantControlPlaneModel.id == tenant_id)).unique().scalar_one_or_none()
            if tenant is None:
                return None
            self._validate_tenant_scope(tenant.id, scoped_tenant_id)
            if idempotency_key:
                existing_event = session.execute(select(BillingEventModel).where(BillingEventModel.idempotency_key == idempotency_key)).scalar_one_or_none()
                if existing_event is not None and existing_event.result_payload.get('tenant_id'):
                    detail = self.get_tenant_detail(existing_event.result_payload['tenant_id'])
                    if detail is not None:
                        return detail
            self._ensure_subscription(session, tenant, plan_key, status, issue_invoice=True)
            if idempotency_key:
                session.add(BillingEventModel(tenant_id=tenant.id, event_type='tenant_plan_assigned', idempotency_key=idempotency_key, payload={'plan_key': plan_key, 'status': status}, result_payload={'tenant_id': tenant.id}))
            self._record_audit(session, actor, 'tenant.assign_plan', 'tenant', tenant.id, tenant.id, 'success', request_id, trace_id, {'plan_key': plan_key, 'status': status})
            session.commit()
            self.cache.invalidate()
            return self.get_tenant_detail(tenant_id)

    def get_tenant_detail(self, tenant_id: str, scoped_tenant_id: str | None = None) -> TenantDetail | None:
        with self.session_factory() as session:
            statement = select(TenantControlPlaneModel).options(joinedload(TenantControlPlaneModel.users), joinedload(TenantControlPlaneModel.subscriptions), joinedload(TenantControlPlaneModel.invoices), joinedload(TenantControlPlaneModel.modules)).where(TenantControlPlaneModel.id == tenant_id)
            tenant = session.execute(statement).unique().scalar_one_or_none()
            if tenant is None:
                return None
            self._validate_tenant_scope(tenant.id, scoped_tenant_id)
            return TenantDetail(tenant=self._to_tenant_record(tenant, len(tenant.users)), users=[self._to_user_record(user) for user in tenant.users], subscriptions=[self._to_subscription_record(item) for item in tenant.subscriptions], invoices=[self._to_invoice_record(item) for item in tenant.invoices], usage=TenantUsageSummary.model_validate(tenant.usage_payload or {}), settings=TenantSettingsRecord.model_validate(tenant.settings_payload or {}), modules=[self._to_module_record(item) for item in tenant.modules])

    def get_dashboard_summary(self) -> DashboardSummary:
        cached = self.cache.get('dashboard')
        if cached is not None:
            return cached
        with self.session_factory() as session:
            tenants = session.execute(select(TenantControlPlaneModel)).scalars().all()
            open_errors = session.scalar(select(func.count()).select_from(ExecutionModel).where(ExecutionModel.status == 'error')) or 0
            active_tenants = sum(1 for tenant in tenants if tenant.status in {'active', 'trialing', 'churn_risk'})
            mrr = round(sum(float(tenant.monthly_recurring_revenue or 0.0) for tenant in tenants), 2)
            health = 'healthy'
            if open_errors >= 3:
                health = 'critical'
            elif open_errors > 0:
                health = 'degraded'
            plan_buckets: dict[str, float] = {}
            region_buckets: dict[str, int] = {}
            for tenant in tenants:
                plan_buckets[tenant.plan] = plan_buckets.get(tenant.plan, 0.0) + float(tenant.monthly_recurring_revenue or 0.0)
                region_buckets[tenant.region] = region_buckets.get(tenant.region, 0) + 1
            return self.cache.set('dashboard', DashboardSummary(mrr=mrr, active_tenants=active_tenants, open_errors=int(open_errors), system_health=health, mrr_delta_percent=8.4, tenant_growth_percent=5.2, system_health_score=max(100 - int(open_errors) * 7, 64), revenue_series=[MetricPoint(label=key, value=value, unit='USD') for key, value in plan_buckets.items()], tenant_distribution=[MetricPoint(label=key, value=float(value), unit='tenants') for key, value in region_buckets.items()]))

    def get_billing_overview(self, status: str | None = None, limit: int = 50, offset: int = 0) -> BillingOverview:
        cache_key = f'billing:{status}:{limit}:{offset}'
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        with self.session_factory() as session:
            subscriptions = session.execute(select(SubscriptionModel).order_by(desc(SubscriptionModel.renewal_date))).scalars().all()
            invoices = session.execute(select(InvoiceModel).order_by(desc(InvoiceModel.issued_at))).scalars().all()
            sub_records = [self._to_subscription_record(item) for item in subscriptions if status in {None, '', item.status}]
            inv_records = [self._to_invoice_record(item) for item in invoices if status in {None, '', item.status}]
            overview = BillingOverview(subscriptions=sub_records[offset: offset + limit], invoices=inv_records[offset: offset + limit], monthly_volume=round(sum(item.amount_monthly for item in sub_records), 2), past_due_total=round(sum(item.total for item in inv_records if item.status == 'past_due'), 2))
            return self.cache.set(cache_key, overview)

    def get_system_health(self, queue_depth: int, active_jobs: int, database_ok: bool, queue_ok: bool) -> SystemHealthSummary:
        with self.session_factory() as session:
            alerts = session.execute(select(SystemAlertModel).order_by(desc(SystemAlertModel.created_at)).limit(10)).scalars().all()
            logs = session.execute(select(ExecutionLogModel).order_by(desc(ExecutionLogModel.created_at)).limit(40)).scalars().all()
            execution_count = session.scalar(select(func.count()).select_from(ExecutionModel)) or 0
            error_count = session.scalar(select(func.count()).select_from(ExecutionModel).where(ExecutionModel.status == 'error')) or 0
            status = 'healthy'
            if not database_ok or not queue_ok or error_count >= 3:
                status = 'critical'
            elif queue_depth > 0 or error_count > 0 or active_jobs > 0:
                status = 'degraded'
            combined_alerts = [self._to_alert_record(item) for item in alerts]
            if not database_ok:
                combined_alerts.insert(0, AlertRecord(id=str(uuid4()), severity='critical', source='database', message='Primary control-plane database healthcheck failed.'))
            if not queue_ok:
                combined_alerts.insert(0, AlertRecord(id=str(uuid4()), severity='critical', source='queue', message='Asynchronous execution queue is unavailable.'))
            return SystemHealthSummary(status=status, logs=[SystemLogRecord(id=item.id, level=item.level, source=item.agent_name, message=item.message, created_at=item.created_at) for item in logs], alerts=combined_alerts, metrics=[MetricPoint(label='queue_depth', value=float(queue_depth), unit='jobs'), MetricPoint(label='active_jobs', value=float(active_jobs), unit='jobs'), MetricPoint(label='executions', value=float(execution_count), unit='runs'), MetricPoint(label='error_runs', value=float(error_count), unit='runs'), MetricPoint(label='database_health', value=1.0 if database_ok else 0.0, unit='binary'), MetricPoint(label='queue_health', value=1.0 if queue_ok else 0.0, unit='binary')])

    def list_users(self, search: str | None = None, role: str | None = None, tenant_id: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[TenantUserRecord], int]:
        with self.session_factory() as session:
            statement = select(TenantUserModel).order_by(TenantUserModel.full_name)
            if tenant_id:
                statement = statement.where(TenantUserModel.tenant_id == tenant_id)
            users = session.execute(statement).scalars().all()
            records = [self._to_user_record(user) for user in users]
            filtered = []
            for user in records:
                if search and search.lower() not in f'{user.full_name} {user.email}'.lower():
                    continue
                if role and user.role != role:
                    continue
                filtered.append(user)
            return filtered[offset: offset + limit], len(filtered)

    def list_roles(self) -> list[RoleRecord]:
        with self.session_factory() as session:
            roles = session.execute(select(RoleModel).order_by(RoleModel.scope, RoleModel.name)).scalars().all()
            return [RoleRecord(id=item.id, name=item.name, scope=item.scope, permissions=item.permissions_payload or []) for item in roles]

    def update_user_role(self, user_id: str, role: str, scoped_tenant_id: str | None = None, actor: str = 'system', request_id: str | None = None, trace_id: str | None = None) -> TenantUserRecord | None:
        with self.session_factory() as session:
            user = session.get(TenantUserModel, user_id)
            if user is None:
                return None
            self._validate_tenant_scope(user.tenant_id, scoped_tenant_id)
            user.role = role
            self._record_audit(session, actor, 'user.role.update', 'user', user.id, user.tenant_id, 'success', request_id, trace_id, {'role': role})
            session.commit()
            self.cache.invalidate()
            return self._to_user_record(user)

    def upsert_role(self, role_id: str | None, name: str, scope: str, permissions: list[str], actor: str = 'system', request_id: str | None = None, trace_id: str | None = None) -> RoleRecord:
        with self.session_factory() as session:
            record = session.get(RoleModel, role_id) if role_id else None
            if record is None:
                record = RoleModel(name=name, scope=scope, permissions_payload=permissions)
                session.add(record)
                session.flush()
            else:
                record.name = name
                record.scope = scope
                record.permissions_payload = permissions
            self._record_audit(session, actor, 'role.upsert', 'role', record.id, None, 'success', request_id, trace_id, {'name': name, 'scope': scope})
            session.commit()
            self.cache.invalidate()
            return RoleRecord(id=record.id, name=record.name, scope=record.scope, permissions=record.permissions_payload or [])

    def list_modules(self, tenant_id: str | None = None, limit: int = 100, offset: int = 0) -> tuple[list[ModuleFlagRecord], int]:
        with self.session_factory() as session:
            statement = select(ModuleFlagModel).order_by(ModuleFlagModel.category, ModuleFlagModel.label)
            if tenant_id:
                statement = statement.where(ModuleFlagModel.tenant_id == tenant_id)
            rows = [self._to_module_record(item) for item in session.execute(statement).scalars().all()]
            return rows[offset: offset + limit], len(rows)

    def update_module_flag(self, module_id: str, enabled: bool, rollout: int, scoped_tenant_id: str | None = None, actor: str = 'system', request_id: str | None = None, trace_id: str | None = None) -> ModuleFlagRecord | None:
        with self.session_factory() as session:
            record = session.get(ModuleFlagModel, module_id)
            if record is None:
                return None
            self._validate_tenant_scope(record.tenant_id, scoped_tenant_id)
            record.enabled = enabled
            record.rollout = rollout
            self._record_audit(session, actor, 'module.update', 'module', record.id, record.tenant_id, 'success', request_id, trace_id, {'enabled': enabled, 'rollout': rollout})
            session.commit()
            self.cache.invalidate()
            return self._to_module_record(record)

    def record_audit_log(self, actor: str, action: str, entity_type: str, entity_id: str | None, tenant_id: str | None, status: str, request_id: str | None, trace_id: str | None, payload: dict | None = None) -> None:
        with self.session_factory() as session:
            self._record_audit(session, actor, action, entity_type, entity_id, tenant_id, status, request_id, trace_id, payload or {})
            session.commit()

    def _record_audit(self, session: Session, actor: str, action: str, entity_type: str, entity_id: str | None, tenant_id: str | None, status: str, request_id: str | None, trace_id: str | None, payload: dict) -> None:
        session.add(AuditLogModel(actor=actor, action=action, entity_type=entity_type, entity_id=entity_id, tenant_id=tenant_id, status=status, request_id=request_id, trace_id=trace_id, payload=sanitize_metadata(payload)))

    def _seed_roles(self, session: Session) -> None:
        if session.scalar(select(func.count()).select_from(RoleModel)):
            return
        session.add_all([RoleModel(name='platform_admin', scope='platform', permissions_payload=['tenants:read', 'tenants:write', 'billing:read', 'health:read', 'roles:write']), RoleModel(name='support_admin', scope='platform', permissions_payload=['tenants:read', 'health:read', 'billing:read']), RoleModel(name='tenant_owner', scope='tenant', permissions_payload=['users:write', 'billing:read', 'modules:write', 'settings:write']), RoleModel(name='tenant_admin', scope='tenant', permissions_payload=['users:write', 'modules:write', 'settings:read']), RoleModel(name='finance_manager', scope='tenant', permissions_payload=['billing:read', 'invoices:read', 'payments:read']), RoleModel(name='sales_manager', scope='tenant', permissions_payload=['crm:read', 'crm:write', 'reports:read'])])

    def _seed_plans(self, session: Session) -> None:
        if session.scalar(select(func.count()).select_from(PlanModel)):
            return
        session.add_all([PlanModel(key='starter', label='Starter', monthly_price=2400.0, included_modules=['finance'], max_users=15), PlanModel(key='growth', label='Growth', monthly_price=6800.0, included_modules=['finance', 'crm', 'inventory'], max_users=75), PlanModel(key='enterprise', label='Enterprise', monthly_price=12400.0, included_modules=['finance', 'crm', 'inventory', 'ai-copilot'], max_users=500)])

    def _create_seed_tenant(self, session: Session, name: str, slug: str, region: str, plan_key: str, status: str, billing_email: str, timezone_name: str, enforce_sso: bool, usage_payload: dict, locale: str = 'en-US') -> TenantControlPlaneModel:
        plan = self._get_plan(session, plan_key)
        tenant = TenantControlPlaneModel(name=name, slug=slug, region=region, plan=plan.key, status=status, monthly_recurring_revenue=plan.monthly_price, settings_payload={'timezone': timezone_name, 'locale': locale, 'billing_email': billing_email, 'enforce_sso': enforce_sso}, usage_payload=usage_payload)
        session.add(tenant)
        session.flush()
        self._sync_modules_for_plan(session, tenant.id, plan)
        return tenant

    def _ensure_subscription(self, session: Session, tenant: TenantControlPlaneModel, plan_key: str, status: str, issue_invoice: bool) -> InvoiceModel | None:
        plan = self._get_plan(session, plan_key)
        tenant.plan = plan.key
        tenant.monthly_recurring_revenue = plan.monthly_price
        tenant.status = 'trialing' if status == 'trialing' else ('churn_risk' if status == 'past_due' else 'active')
        active_subscriptions = session.execute(select(SubscriptionModel).where(SubscriptionModel.tenant_id == tenant.id)).scalars().all()
        for subscription in active_subscriptions:
            subscription.status = 'cancelled' if subscription.status != status else subscription.status
        session.add(SubscriptionModel(tenant_id=tenant.id, plan=plan.key, status=status, amount_monthly=plan.monthly_price, currency=plan.currency, billing_cycle='monthly', renewal_date=datetime.now(timezone.utc) + timedelta(days=30)))
        self._sync_modules_for_plan(session, tenant.id, plan)
        if not issue_invoice:
            return None
        invoice = InvoiceModel(tenant_id=tenant.id, number=f'INV-{datetime.now(timezone.utc).year}-{uuid4().hex[:6].upper()}', status='open' if status in {'active', 'trialing'} else ('past_due' if status == 'past_due' else 'void'), total=plan.monthly_price, currency=plan.currency, due_date=datetime.now(timezone.utc) + timedelta(days=14), issued_at=datetime.now(timezone.utc))
        session.add(invoice)
        return invoice

    def _sync_modules_for_plan(self, session: Session, tenant_id: str, plan: PlanModel) -> None:
        existing = session.execute(select(ModuleFlagModel).where(ModuleFlagModel.tenant_id == tenant_id)).scalars().all()
        by_key = {item.key: item for item in existing}
        required_modules = {'finance', 'crm', 'inventory', 'ai-copilot'}
        metadata = {'finance': ('Finance', 'erp'), 'crm': ('CRM', 'erp'), 'inventory': ('Inventory', 'erp'), 'ai-copilot': ('AI Copilot', 'platform')}
        for key in required_modules:
            label, category = metadata[key]
            record = by_key.get(key)
            enabled = key in set(plan.included_modules or []) or key == 'finance'
            if record is None:
                session.add(ModuleFlagModel(tenant_id=tenant_id, key=key, label=label, category=category, enabled=enabled, rollout=100 if enabled else 0))
            else:
                record.enabled = enabled
                record.rollout = 100 if enabled else 0

    def _get_plan(self, session: Session, plan_key: str) -> PlanModel:
        plan = session.execute(select(PlanModel).where(PlanModel.key == plan_key)).scalar_one_or_none()
        if plan is None:
            raise ValueError(f'Plan not found: {plan_key}')
        return plan

    def _validate_tenant_scope(self, entity_tenant_id: str | None, scoped_tenant_id: str | None) -> None:
        if scoped_tenant_id and entity_tenant_id and scoped_tenant_id != entity_tenant_id:
            raise PermissionError('Tenant scope mismatch detected.')

    def _matches_tenant(self, item: TenantRecord, search: str | None, status: str | None) -> bool:
        if search and search.lower() not in f'{item.name} {item.slug} {item.region} {item.plan}'.lower():
            return False
        if status and item.status != status:
            return False
        return True

    def _to_tenant_record(self, tenant: TenantControlPlaneModel, active_users: int) -> TenantRecord:
        return TenantRecord(id=tenant.id, name=tenant.name, slug=tenant.slug, region=tenant.region, plan=tenant.plan, status=tenant.status, monthly_recurring_revenue=float(tenant.monthly_recurring_revenue or 0.0), active_users=active_users, created_at=tenant.created_at)

    def _to_user_record(self, user: TenantUserModel) -> TenantUserRecord:
        return TenantUserRecord(id=user.id, tenant_id=user.tenant_id, full_name=user.full_name, email=user.email, role=user.role, status=user.status, last_active_at=user.last_active_at)

    def _to_subscription_record(self, item: SubscriptionModel) -> SubscriptionRecord:
        return SubscriptionRecord(id=item.id, tenant_id=item.tenant_id, plan=item.plan, status=item.status, amount_monthly=float(item.amount_monthly or 0.0), currency=item.currency, billing_cycle=item.billing_cycle, renewal_date=item.renewal_date)

    def _to_invoice_record(self, item: InvoiceModel) -> InvoiceRecord:
        return InvoiceRecord(id=item.id, tenant_id=item.tenant_id, number=item.number, status=item.status, total=float(item.total or 0.0), currency=item.currency, due_date=item.due_date, issued_at=item.issued_at)

    def _to_module_record(self, item: ModuleFlagModel) -> ModuleFlagRecord:
        return ModuleFlagRecord(id=item.id, tenant_id=item.tenant_id, key=item.key, label=item.label, category=item.category, enabled=item.enabled, rollout=item.rollout)

    def _to_alert_record(self, item: SystemAlertModel) -> AlertRecord:
        return AlertRecord(id=item.id, severity=item.severity, source=item.source, message=item.message, created_at=item.created_at)

    def _to_plan_record(self, item: PlanModel) -> PlanRecord:
        return PlanRecord(id=item.id, key=item.key, label=item.label, currency=item.currency, monthly_price=float(item.monthly_price or 0.0), included_modules=item.included_modules or [], max_users=item.max_users, status=item.status)

    def _to_audit_record(self, item: AuditLogModel) -> AuditLogRecord:
        return AuditLogRecord(id=item.id, actor=item.actor, action=item.action, entity_type=item.entity_type, entity_id=item.entity_id, tenant_id=item.tenant_id, status=item.status, request_id=item.request_id, trace_id=item.trace_id, payload=item.payload or {}, created_at=item.created_at)
