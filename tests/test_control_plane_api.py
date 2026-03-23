from __future__ import annotations

from fastapi.testclient import TestClient

from apps.orchestrator.main import app, get_control_plane_repository, get_dispatcher, get_repository, get_settings


def _reset_caches():
    get_settings.cache_clear()
    get_dispatcher.cache_clear()
    get_repository.cache_clear()
    get_control_plane_repository.cache_clear()
    
    
def _reset_runtime_state():
    from apps.orchestrator.main import get_metrics_registry, get_rate_limiter, get_runtime_cache, get_tracer

    get_metrics_registry.cache_clear()
    get_rate_limiter.cache_clear()
    get_runtime_cache.cache_clear()
    get_tracer.cache_clear()


def test_control_plane_auth_login_and_session(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'control-plane-auth.db'}"
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setenv('COREFLOW_ASYNC_BACKEND', 'memory')
    monkeypatch.setenv('COREFLOW_ADMIN_USERNAME', 'admin')
    monkeypatch.setenv('COREFLOW_ADMIN_PASSWORD', 'admin123')
    monkeypatch.setenv('COREFLOW_API_TOKEN', 'local-token')
    _reset_caches()
    _reset_runtime_state()

    client = TestClient(app)
    login_response = client.post('/api/control-plane/auth/login', json={'username': 'admin', 'password': 'admin123'})

    assert login_response.status_code == 200
    session = login_response.json()
    assert session['access_token']
    session_response = client.get('/api/control-plane/auth/session', headers={'Authorization': f"Bearer {session['access_token']}"})
    assert session_response.status_code == 200
    assert session_response.json()['authenticated'] is True
    assert session_response.json()['session']['username'] == 'admin'

    _reset_caches()
    _reset_runtime_state()


def test_control_plane_create_tenant_assign_plan_and_view_billing(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'control-plane-flow.db'}"
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setenv('COREFLOW_ASYNC_BACKEND', 'memory')
    monkeypatch.setenv('COREFLOW_API_TOKEN', 'local-token')
    _reset_caches()
    _reset_runtime_state()

    client = TestClient(app)
    headers = {'Authorization': 'Bearer local-token'}

    plans_response = client.get('/api/control-plane/plans', headers=headers)
    assert plans_response.status_code == 200
    plans = plans_response.json()
    assert any(plan['key'] == 'growth' for plan in plans)

    create_response = client.post(
        '/api/control-plane/tenants',
        headers=headers,
        json={
            'name': 'Atlas Manufacturing',
            'slug': 'atlas-manufacturing',
            'region': 'eu-central-1',
            'plan_key': 'starter',
            'billing_email': 'billing@atlas.test',
            'timezone': 'Europe/Berlin',
            'locale': 'en-DE',
            'enforce_sso': True,
        },
    )
    assert create_response.status_code == 200
    created_tenant = create_response.json()
    tenant_id = created_tenant['tenant']['id']
    assert created_tenant['tenant']['plan'] == 'starter'
    assert created_tenant['settings']['billing_email'] == 'billing@atlas.test'

    assign_response = client.patch(
        f'/api/control-plane/tenants/{tenant_id}/plan',
        headers=headers,
        json={'plan_key': 'enterprise', 'status': 'active'},
    )
    assert assign_response.status_code == 200
    assigned = assign_response.json()
    assert assigned['tenant']['plan'] == 'enterprise'
    assert any(item['plan'] == 'enterprise' for item in assigned['subscriptions'])

    billing_response = client.get('/api/control-plane/billing', headers=headers)
    assert billing_response.status_code == 200
    billing = billing_response.json()
    assert any(item['tenant_id'] == tenant_id and item['plan'] == 'enterprise' for item in billing['subscriptions'])
    assert any(item['tenant_id'] == tenant_id for item in billing['invoices'])

    _reset_caches()


def test_control_plane_endpoints_return_seeded_data(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'control-plane.db'}"
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setenv('COREFLOW_ASYNC_BACKEND', 'memory')
    monkeypatch.setenv('COREFLOW_API_TOKEN', 'local-token')
    _reset_caches()

    client = TestClient(app)
    headers = {'Authorization': 'Bearer local-token'}

    dashboard = client.get('/api/control-plane/dashboard', headers=headers)
    tenants = client.get('/api/control-plane/tenants', headers=headers)
    billing = client.get('/api/control-plane/billing', headers=headers)
    users = client.get('/api/control-plane/users', headers=headers)
    modules = client.get('/api/control-plane/modules', headers=headers)

    assert dashboard.status_code == 200
    assert dashboard.json()['mrr'] > 0
    assert tenants.status_code == 200
    assert len(tenants.json()['items']) >= 1
    assert tenants.json()['total'] >= len(tenants.json()['items'])
    assert billing.status_code == 200
    assert len(billing.json()['subscriptions']) >= 1
    assert users.status_code == 200
    assert len(users.json()['items']) >= 1
    assert modules.status_code == 200
    assert len(modules.json()['items']) >= 1

    tenant_id = tenants.json()['items'][0]['id']
    tenant_detail = client.get(f'/api/control-plane/tenants/{tenant_id}', headers=headers)
    assert tenant_detail.status_code == 200
    assert tenant_detail.json()['tenant']['id'] == tenant_id

    _reset_caches()
    _reset_runtime_state()


def test_control_plane_role_and_module_updates(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'control-plane-update.db'}"
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setenv('COREFLOW_ASYNC_BACKEND', 'memory')
    monkeypatch.setenv('COREFLOW_API_TOKEN', 'local-token')
    _reset_caches()
    _reset_runtime_state()

    client = TestClient(app)
    headers = {'Authorization': 'Bearer local-token'}

    users = client.get('/api/control-plane/users', headers=headers).json()['items']
    modules = client.get('/api/control-plane/modules', headers=headers).json()['items']

    user_update = client.patch(
        f"/api/control-plane/users/{users[0]['id']}/role",
        headers={**headers, 'X-Tenant-Id': users[0]['tenant_id']},
        json={'role': 'support_admin'},
    )
    module_update = client.patch(
        f"/api/control-plane/modules/{modules[0]['id']}",
        headers={**headers, 'X-Tenant-Id': modules[0]['tenant_id']},
        json={'enabled': False, 'rollout': 40},
    )

    assert user_update.status_code == 200
    assert user_update.json()['role'] == 'support_admin'
    assert module_update.status_code == 200
    assert module_update.json()['enabled'] is False
    assert module_update.json()['rollout'] == 40

    _reset_caches()
    _reset_runtime_state()


def test_admin_static_ui_is_served():
    client = TestClient(app)
    response = client.get('/admin/')

    assert response.status_code == 200
    assert 'CoreFlow Control Plane' in response.text


def test_control_plane_security_headers_audit_and_metrics(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'control-plane-security.db'}"
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setenv('COREFLOW_ASYNC_BACKEND', 'memory')
    monkeypatch.setenv('COREFLOW_API_TOKEN', 'local-token')
    _reset_caches()
    _reset_runtime_state()

    client = TestClient(app)
    headers = {'Authorization': 'Bearer local-token'}

    tenant_response = client.post(
        '/api/control-plane/tenants',
        headers={**headers, 'Idempotency-Key': 'tenant-create-1'},
        json={
            'name': 'Orbit Foods',
            'slug': 'orbit-foods',
            'region': 'us-east-1',
            'plan_key': 'starter',
            'billing_email': 'finance@orbit.test',
            'timezone': 'UTC',
            'locale': 'en-US',
            'enforce_sso': False,
        },
    )

    assert tenant_response.status_code == 200
    assert tenant_response.headers['x-content-type-options'] == 'nosniff'
    assert tenant_response.headers['x-frame-options'] == 'DENY'
    assert tenant_response.headers['cache-control'] == 'no-store'
    assert tenant_response.headers['x-request-id']
    assert tenant_response.headers['x-trace-id']

    audit_response = client.get('/api/control-plane/audit-logs', headers=headers)
    metrics_response = client.get('/metrics', headers=headers)

    assert audit_response.status_code == 200
    assert any(item['action'] == 'tenant.create' for item in audit_response.json()['items'])
    assert metrics_response.status_code == 200
    assert metrics_response.json()['counters']['http.requests'] >= 1


def test_control_plane_rate_limit_idempotency_and_tenant_isolation(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'control-plane-isolation.db'}"
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setenv('COREFLOW_ASYNC_BACKEND', 'memory')
    monkeypatch.setenv('COREFLOW_API_TOKEN', 'local-token')
    monkeypatch.setenv('COREFLOW_RATE_LIMIT_REQUESTS', '50')
    monkeypatch.setenv('COREFLOW_LOGIN_RATE_LIMIT_REQUESTS', '1')
    _reset_caches()
    _reset_runtime_state()

    client = TestClient(app)
    headers = {'Authorization': 'Bearer local-token'}

    create_response = client.post(
        '/api/control-plane/tenants',
        headers={**headers, 'Idempotency-Key': 'tenant-create-idempotent'},
        json={
            'name': 'Helios Systems',
            'slug': 'helios-systems',
            'region': 'us-west-2',
            'plan_key': 'starter',
            'billing_email': 'ops@helios.test',
            'timezone': 'UTC',
            'locale': 'en-US',
            'enforce_sso': True,
        },
    )
    replay_response = client.post(
        '/api/control-plane/tenants',
        headers={**headers, 'Idempotency-Key': 'tenant-create-idempotent'},
        json={
            'name': 'Helios Systems',
            'slug': 'helios-systems',
            'region': 'us-west-2',
            'plan_key': 'starter',
            'billing_email': 'ops@helios.test',
            'timezone': 'UTC',
            'locale': 'en-US',
            'enforce_sso': True,
        },
    )

    assert create_response.status_code == 200
    assert replay_response.status_code == 200
    assert create_response.json()['tenant']['id'] == replay_response.json()['tenant']['id']

    tenant_id = create_response.json()['tenant']['id']
    denied_response = client.get(
        f'/api/control-plane/tenants/{tenant_id}',
        headers={**headers, 'X-Tenant-Id': 'wrong-tenant'},
    )
    assert denied_response.status_code == 403

    login_1 = client.post('/api/control-plane/auth/login', json={'username': 'admin', 'password': 'admin123'})
    login_2 = client.post('/api/control-plane/auth/login', json={'username': 'admin', 'password': 'admin123'})
    assert login_1.status_code == 200
    assert login_2.status_code == 429
