from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CoreFlowSettings:
    database_url: str
    api_token: str
    default_provider: str
    max_concurrent_jobs: int
    enforce_auth: bool
    async_backend: str
    redis_url: str
    redis_queue_name: str
    worker_poll_timeout_seconds: int
    admin_username: str
    admin_password: str
    admin_email: str
    admin_name: str
    seed_tenant_name: str
    seed_tenant_plan: str
    seed_tenant_status: str
    auth_secret: str
    auth_token_ttl_seconds: int
    cache_ttl_seconds: int
    rate_limit_requests: int
    rate_limit_window_seconds: int
    login_rate_limit_requests: int
    login_rate_limit_window_seconds: int
    distributed_rate_limit_enabled: bool
    distributed_rate_limit_prefix: str
    tracing_enabled: bool
    tracing_service_name: str
    prometheus_namespace: str

    @classmethod
    def from_env(cls) -> 'CoreFlowSettings':
        default_admin_username = os.getenv('COREFLOW_ADMIN_USERNAME', 'admin')
        return cls(
            database_url=os.getenv('DATABASE_URL', 'sqlite:///./.coreflow/coreflow.db'),
            api_token=os.getenv('COREFLOW_API_TOKEN', 'local-token'),
            default_provider=os.getenv('COREFLOW_LLM_PROVIDER', 'template'),
            max_concurrent_jobs=int(os.getenv('COREFLOW_MAX_CONCURRENT_JOBS', '4')),
            enforce_auth=os.getenv('COREFLOW_ENFORCE_AUTH', 'true').lower() in {'1', 'true', 'yes', 'on'},
            async_backend=os.getenv('COREFLOW_ASYNC_BACKEND', 'memory').lower(),
            redis_url=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
            redis_queue_name=os.getenv('COREFLOW_REDIS_QUEUE', 'coreflow:jobs'),
            worker_poll_timeout_seconds=int(os.getenv('COREFLOW_WORKER_POLL_TIMEOUT', '5')),
            admin_username=default_admin_username,
            admin_password=os.getenv('COREFLOW_ADMIN_PASSWORD', 'admin123'),
            admin_email=os.getenv('COREFLOW_ADMIN_EMAIL', 'admin@plataformaerp.local'),
            admin_name=os.getenv('COREFLOW_ADMIN_NAME', default_admin_username),
            seed_tenant_name=os.getenv('COREFLOW_SEED_TENANT_NAME', 'PlataformaERP'),
            seed_tenant_plan=os.getenv('COREFLOW_SEED_TENANT_PLAN', 'enterprise'),
            seed_tenant_status=os.getenv('COREFLOW_SEED_TENANT_STATUS', 'active'),
            auth_secret=os.getenv('COREFLOW_AUTH_SECRET', os.getenv('COREFLOW_API_TOKEN', 'local-token')),
            auth_token_ttl_seconds=int(os.getenv('COREFLOW_AUTH_TOKEN_TTL', '28800')),
            cache_ttl_seconds=int(os.getenv('COREFLOW_CACHE_TTL_SECONDS', '15')),
            rate_limit_requests=int(os.getenv('COREFLOW_RATE_LIMIT_REQUESTS', '120')),
            rate_limit_window_seconds=int(os.getenv('COREFLOW_RATE_LIMIT_WINDOW_SECONDS', '60')),
            login_rate_limit_requests=int(os.getenv('COREFLOW_LOGIN_RATE_LIMIT_REQUESTS', '10')),
            login_rate_limit_window_seconds=int(os.getenv('COREFLOW_LOGIN_RATE_LIMIT_WINDOW_SECONDS', '60')),
            distributed_rate_limit_enabled=os.getenv('COREFLOW_DISTRIBUTED_RATE_LIMIT', 'false').lower() in {'1', 'true', 'yes', 'on'},
            distributed_rate_limit_prefix=os.getenv('COREFLOW_DISTRIBUTED_RATE_LIMIT_PREFIX', 'coreflow:ratelimit'),
            tracing_enabled=os.getenv('COREFLOW_TRACING_ENABLED', 'true').lower() in {'1', 'true', 'yes', 'on'},
            tracing_service_name=os.getenv('COREFLOW_TRACING_SERVICE', 'coreflow-orchestrator'),
            prometheus_namespace=os.getenv('COREFLOW_PROMETHEUS_NAMESPACE', 'coreflow'),
        )
