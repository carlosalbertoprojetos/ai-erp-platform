from __future__ import annotations

import jwt
from fastapi.testclient import TestClient

from apps.orchestrator.main import app, get_control_plane_repository, get_dispatcher, get_iam_repository, get_repository, get_settings


def _reset_caches():
    get_settings.cache_clear()
    get_dispatcher.cache_clear()
    get_repository.cache_clear()
    get_control_plane_repository.cache_clear()
    get_iam_repository.cache_clear()


def _reset_runtime_state():
    from apps.orchestrator.main import get_metrics_registry, get_rate_limiter, get_runtime_cache, get_tracer

    get_metrics_registry.cache_clear()
    get_rate_limiter.cache_clear()
    get_runtime_cache.cache_clear()
    get_tracer.cache_clear()


def _login(client: TestClient, username: str = 'admin', password: str = 'admin123') -> dict:
    response = client.post('/auth/login', json={'username': username, 'password': password})
    assert response.status_code == 200
    return response.json()


def test_auth_login_and_session_include_jwt_claims(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'iam-auth.db'}"
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setenv('COREFLOW_ASYNC_BACKEND', 'memory')
    monkeypatch.setenv('COREFLOW_ADMIN_USERNAME', 'admin')
    monkeypatch.setenv('COREFLOW_ADMIN_PASSWORD', 'admin123')
    monkeypatch.setenv('COREFLOW_ADMIN_EMAIL', 'admin@plataformaerp.local')
    monkeypatch.setenv('COREFLOW_AUTH_SECRET', 'jwt-secret-with-32-bytes-minimum')
    _reset_caches()
    _reset_runtime_state()

    client = TestClient(app)
    session = _login(client)

    assert session['access_token']
    assert session['user']['roles'] == ['admin']
    assert sorted(session['user']['modules']) == ['crm', 'finance', 'products', 'sales']

    claims = jwt.decode(session['access_token'], 'jwt-secret-with-32-bytes-minimum', algorithms=['HS256'])
    assert claims['sub'] == session['user']['id']
    assert claims['tenant_id'] == session['user']['tenant_id']
    assert claims['roles'] == ['admin']
    assert sorted(claims['modules']) == ['crm', 'finance', 'products', 'sales']

    session_response = client.get('/auth/session', headers={'Authorization': f"Bearer {session['access_token']}"})
    assert session_response.status_code == 200
    assert session_response.json()['authenticated'] is True
    assert session_response.json()['principal']['tenant_id'] == session['user']['tenant_id']

    me_response = client.get('/auth/me', headers={'Authorization': f"Bearer {session['access_token']}"})
    assert me_response.status_code == 200
    assert me_response.json()['email'] == 'admin@plataformaerp.local'

    _reset_caches()
    _reset_runtime_state()


def test_seed_data_and_tenant_endpoints(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'iam-seed.db'}"
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setenv('COREFLOW_ASYNC_BACKEND', 'memory')
    monkeypatch.setenv('COREFLOW_AUTH_SECRET', 'jwt-secret-with-32-bytes-minimum')
    _reset_caches()
    _reset_runtime_state()

    client = TestClient(app)
    session = _login(client)
    headers = {'Authorization': f"Bearer {session['access_token']}"}

    tenants = client.get('/tenants', headers=headers)
    roles = client.get('/roles', headers=headers)
    modules = client.get('/modules', headers=headers)
    users = client.get('/users', headers=headers)

    assert tenants.status_code == 200
    assert len(tenants.json()) == 1
    assert tenants.json()[0]['name'] == 'PlataformaERP'
    assert roles.status_code == 200
    assert sorted(item['name'] for item in roles.json()) == ['admin', 'manager', 'user']
    assert modules.status_code == 200
    assert sorted(item['name'] for item in modules.json()) == ['crm', 'finance', 'products', 'sales']
    assert users.status_code == 200
    assert len(users.json()) == 1
    assert users.json()[0]['email'] == 'admin@plataformaerp.local'

    create_tenant = client.post('/tenants', headers=headers, json={'name': 'Tenant Beta', 'plan': 'growth', 'status': 'active'})
    assert create_tenant.status_code == 200
    assert create_tenant.json()['name'] == 'Tenant Beta'

    tenant_detail = client.get(f"/tenants/{create_tenant.json()['id']}", headers=headers)
    assert tenant_detail.status_code == 200
    assert tenant_detail.json()['plan'] == 'growth'

    _reset_caches()
    _reset_runtime_state()


def test_user_crud_assignments_and_tenant_isolation(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'iam-users.db'}"
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setenv('COREFLOW_ASYNC_BACKEND', 'memory')
    monkeypatch.setenv('COREFLOW_AUTH_SECRET', 'jwt-secret-with-32-bytes-minimum')
    _reset_caches()
    _reset_runtime_state()

    client = TestClient(app)
    admin_session = _login(client)
    admin_headers = {'Authorization': f"Bearer {admin_session['access_token']}"}

    create_tenant = client.post('/tenants', headers=admin_headers, json={'name': 'Tenant Gamma', 'plan': 'enterprise', 'status': 'active'})
    assert create_tenant.status_code == 200
    tenant_id = create_tenant.json()['id']

    create_user = client.post(
        '/users',
        headers=admin_headers,
        json={
            'name': 'Maria Manager',
            'email': 'maria@gamma.test',
            'password': 'secret123',
            'tenant_id': tenant_id,
            'roles': ['manager'],
            'modules': ['crm', 'sales'],
            'is_active': True,
        },
    )
    assert create_user.status_code == 200
    created_user = create_user.json()
    assert created_user['tenant_id'] == tenant_id
    assert created_user['roles'] == ['manager']
    assert sorted(created_user['modules']) == ['crm', 'sales']

    update_user = client.patch(
        f"/users/{created_user['id']}",
        headers=admin_headers,
        json={'tenant_id': tenant_id, 'name': 'Maria Updated', 'is_active': True},
    )
    assert update_user.status_code == 200
    assert update_user.json()['name'] == 'Maria Updated'

    assign_roles = client.put(
        f"/users/{created_user['id']}/roles",
        headers=admin_headers,
        json={'tenant_id': tenant_id, 'roles': ['user']},
    )
    assign_modules = client.put(
        f"/users/{created_user['id']}/modules",
        headers=admin_headers,
        json={'tenant_id': tenant_id, 'modules': ['finance']},
    )
    assert assign_roles.status_code == 200
    assert assign_roles.json()['roles'] == ['user']
    assert assign_modules.status_code == 200
    assert assign_modules.json()['modules'] == ['finance']

    gamma_users = client.get(f'/users?tenant_id={tenant_id}', headers=admin_headers)
    assert gamma_users.status_code == 200
    assert len(gamma_users.json()) == 1

    user_session = _login(client, username='maria@gamma.test', password='secret123')
    user_headers = {'Authorization': f"Bearer {user_session['access_token']}"}

    finance_access = client.get('/auth/access/finance', headers=user_headers)
    crm_access = client.get('/auth/access/crm', headers=user_headers)
    own_scope_users = client.get('/users', headers=user_headers)
    foreign_scope_users = client.get(f"/users?tenant_id={admin_session['user']['tenant_id']}", headers=user_headers)
    forbidden_tenant_create = client.post('/tenants', headers=user_headers, json={'name': 'Blocked Tenant', 'plan': 'starter', 'status': 'active'})

    assert finance_access.status_code == 200
    assert crm_access.status_code == 403
    assert own_scope_users.status_code == 200
    assert len(own_scope_users.json()) == 1
    assert foreign_scope_users.status_code == 403
    assert forbidden_tenant_create.status_code == 403

    _reset_caches()
    _reset_runtime_state()


def _seed_control_plane() -> None:
    repository = get_control_plane_repository()
    repository.ensure_schema()
    repository.seed_defaults()


def test_legacy_control_plane_seeded_endpoints_still_work(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'control-plane-seeded.db'}"
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setenv('COREFLOW_ASYNC_BACKEND', 'memory')
    monkeypatch.setenv('COREFLOW_API_TOKEN', 'local-token')
    monkeypatch.setenv('COREFLOW_AUTH_SECRET', 'jwt-secret-with-32-bytes-minimum')
    _reset_caches()
    _reset_runtime_state()
    _seed_control_plane()

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


def test_legacy_control_plane_create_tenant_assign_plan_and_billing(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'control-plane-flow.db'}"
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setenv('COREFLOW_ASYNC_BACKEND', 'memory')
    monkeypatch.setenv('COREFLOW_API_TOKEN', 'local-token')
    monkeypatch.setenv('COREFLOW_AUTH_SECRET', 'jwt-secret-with-32-bytes-minimum')
    _reset_caches()
    _reset_runtime_state()
    _seed_control_plane()

    client = TestClient(app)
    headers = {'Authorization': 'Bearer local-token'}

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

    assign_response = client.patch(
        f'/api/control-plane/tenants/{tenant_id}/plan',
        headers=headers,
        json={'plan_key': 'enterprise', 'status': 'active'},
    )
    assert assign_response.status_code == 200
    assert assign_response.json()['tenant']['plan'] == 'enterprise'

    billing_response = client.get('/api/control-plane/billing', headers=headers)
    assert billing_response.status_code == 200
    assert any(item['tenant_id'] == tenant_id for item in billing_response.json()['subscriptions'])
    assert any(item['tenant_id'] == tenant_id for item in billing_response.json()['invoices'])

    _reset_caches()
    _reset_runtime_state()


def test_legacy_control_plane_role_module_audit_and_rate_limit(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'control-plane-security.db'}"
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setenv('COREFLOW_ASYNC_BACKEND', 'memory')
    monkeypatch.setenv('COREFLOW_API_TOKEN', 'local-token')
    monkeypatch.setenv('COREFLOW_AUTH_SECRET', 'jwt-secret-with-32-bytes-minimum')
    monkeypatch.setenv('COREFLOW_RATE_LIMIT_REQUESTS', '50')
    monkeypatch.setenv('COREFLOW_LOGIN_RATE_LIMIT_REQUESTS', '1')
    _reset_caches()
    _reset_runtime_state()
    _seed_control_plane()

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

    assert user_update.status_code == 200
    assert module_update.status_code == 200
    assert create_response.status_code == 200
    assert replay_response.status_code == 200
    assert create_response.json()['tenant']['id'] == replay_response.json()['tenant']['id']

    tenant_id = create_response.json()['tenant']['id']
    denied_response = client.get(
        f'/api/control-plane/tenants/{tenant_id}',
        headers={**headers, 'X-Tenant-Id': 'wrong-tenant'},
    )
    audit_response = client.get('/api/control-plane/audit-logs', headers=headers)
    metrics_response = client.get('/metrics', headers=headers)
    login_1 = client.post('/api/control-plane/auth/login', json={'username': 'admin', 'password': 'admin123'})
    login_2 = client.post('/api/control-plane/auth/login', json={'username': 'admin', 'password': 'admin123'})

    assert denied_response.status_code == 403
    assert audit_response.status_code == 200
    assert any(item['action'] == 'tenant.create' for item in audit_response.json()['items'])
    assert metrics_response.status_code == 200
    assert login_1.status_code == 200
    assert login_2.status_code == 429

    _reset_caches()
    _reset_runtime_state()

