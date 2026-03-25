from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import jwt


@dataclass
class CaseResult:
    name: str
    expected: str
    actual_status: int | None
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


class IntegrationValidator:
    def __init__(self) -> None:
        self.auth_base_url = os.getenv('AUTH_BASE_URL', 'http://127.0.0.1:8100').rstrip('/')
        self.product_base_url = os.getenv('PRODUCT_BASE_URL', 'http://127.0.0.1:3000').rstrip('/')
        self.admin_username = os.getenv('AUTH_ADMIN_USERNAME', 'admin')
        self.admin_password = os.getenv('AUTH_ADMIN_PASSWORD', 'admin123')
        self.auth_secret = os.getenv('AUTH_SECRET', 'jwt-secret-with-32-bytes-minimum')
        self.timeout = float(os.getenv('INTEGRATION_TIMEOUT_SECONDS', '15'))
        self.run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        self.results: list[CaseResult] = []
        self.vulnerabilities: list[str] = []
        self.client = httpx.Client(timeout=self.timeout)

    def close(self) -> None:
        self.client.close()

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        response = self.client.request(method, url, **kwargs)
        return response

    def login(self, username: str, password: str) -> dict[str, Any]:
        response = self.request(
            'POST',
            f'{self.auth_base_url}/auth/login',
            json={'username': username, 'password': password},
        )
        response.raise_for_status()
        return response.json()

    def create_tenant(self, admin_token: str, name: str, plan: str = 'enterprise') -> dict[str, Any]:
        response = self.request(
            'POST',
            f'{self.auth_base_url}/tenants',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'name': name, 'plan': plan, 'status': 'active'},
        )
        response.raise_for_status()
        return response.json()

    def create_user(
        self,
        admin_token: str,
        tenant_id: str,
        name: str,
        email: str,
        password: str,
        modules: list[str],
        roles: list[str] | None = None,
    ) -> dict[str, Any]:
        response = self.request(
            'POST',
            f'{self.auth_base_url}/users',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'tenant_id': tenant_id,
                'name': name,
                'email': email,
                'password': password,
                'is_active': True,
                'roles': roles or ['user'],
                'modules': modules,
            },
        )
        response.raise_for_status()
        return response.json()

    def update_modules(self, admin_token: str, tenant_id: str, user_id: str, modules: list[str]) -> dict[str, Any]:
        response = self.request(
            'PUT',
            f'{self.auth_base_url}/users/{user_id}/modules',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'tenant_id': tenant_id, 'modules': modules},
        )
        response.raise_for_status()
        return response.json()

    def make_product_payload(self, label: str) -> dict[str, Any]:
        return {
            'name': f'Integration Product {label} {uuid4().hex[:8]}',
            'description': 'Automated integration validation payload',
            'type': 'PRODUCT',
            'prices': [{'price': 199.9, 'currency': 'BRL', 'pricingTable': 'padrao'}],
            'stocks': [{'quantity': 3, 'location': 'QA-CD'}],
            'variants': [{'name': 'default', 'attributes': {'suite': 'integration'}}],
        }

    def call_products_create(self, tenant_id: str, token: str | None, label: str) -> httpx.Response:
        headers = {'x-tenant-id': tenant_id}
        if token is not None:
            headers['Authorization'] = f'Bearer {token}'
        return self.request(
            'POST',
            f'{self.product_base_url}/products',
            headers=headers,
            json=self.make_product_payload(label),
        )

    def call_products_get(self, tenant_id: str, token: str | None, product_id: str) -> httpx.Response:
        headers = {'x-tenant-id': tenant_id}
        if token is not None:
            headers['Authorization'] = f'Bearer {token}'
        return self.request('GET', f'{self.product_base_url}/products/{product_id}', headers=headers)

    def build_expired_token(self, valid_token: str) -> str:
        payload = jwt.decode(valid_token, options={'verify_signature': False})
        payload['iat'] = int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp())
        payload['exp'] = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
        return jwt.encode(payload, self.auth_secret, algorithm='HS256')

    def record(self, name: str, expected: str, response: httpx.Response | None, passed: bool, **details: Any) -> None:
        body_preview: Any = None
        if response is not None:
            try:
                body_preview = response.json()
            except Exception:
                body_preview = response.text[:500]
        details['response_body'] = body_preview
        self.results.append(
            CaseResult(
                name=name,
                expected=expected,
                actual_status=None if response is None else response.status_code,
                passed=passed,
                details=details,
            )
        )

    def run(self) -> dict[str, Any]:
        admin_session = self.login(self.admin_username, self.admin_password)
        admin_token = admin_session['access_token']

        suffix = uuid4().hex[:6]
        tenant_a = self.create_tenant(admin_token, f'Integration Tenant A {suffix}')
        tenant_b = self.create_tenant(admin_token, f'Integration Tenant B {suffix}')

        user_a_password = 'Products123!'
        user_b_password = 'Products123!'
        user_a = self.create_user(
            admin_token,
            tenant_a['id'],
            'User Tenant A',
            f'user-a-{suffix}@integration.test',
            user_a_password,
            modules=['products'],
        )
        user_b = self.create_user(
            admin_token,
            tenant_b['id'],
            'User Tenant B',
            f'user-b-{suffix}@integration.test',
            user_b_password,
            modules=['products'],
        )

        session_a = self.login(user_a['email'], user_a_password)
        session_b = self.login(user_b['email'], user_b_password)
        token_a = session_a['access_token']
        token_b = session_b['access_token']

        auth_session = self.request('GET', f'{self.auth_base_url}/auth/session', headers={'Authorization': f'Bearer {token_a}'})
        self.record(
            'auth_login_and_jwt',
            '200 with valid JWT claims',
            auth_session,
            auth_session.status_code == 200,
            user_id=session_a['user']['id'],
            tenant_id=session_a['user']['tenant_id'],
            modules=session_a['user']['modules'],
        )

        allowed_response = self.call_products_create(tenant_a['id'], token_a, 'allowed')
        allowed_ok = allowed_response.status_code in {200, 201}
        self.record('products_access_allowed', '2xx success for products-enabled user', allowed_response, allowed_ok)

        product_a_id = None
        if allowed_ok:
            try:
                product_a_id = allowed_response.json().get('id')
            except Exception:
                product_a_id = None

        self.update_modules(admin_token, tenant_a['id'], user_a['id'], [])
        token_a_without_products = self.login(user_a['email'], user_a_password)['access_token']
        denied_response = self.call_products_create(tenant_a['id'], token_a_without_products, 'denied')
        denied_ok = denied_response.status_code == 403
        self.record('products_access_denied_after_module_removal', '403 forbidden after removing products module', denied_response, denied_ok)
        if not denied_ok:
            self.vulnerabilities.append('product-erp does not enforce module-based access from JWT claims.')

        product_b_response = self.call_products_create(tenant_b['id'], token_b, 'tenant-b')
        product_b_id = None
        if product_b_response.status_code in {200, 201}:
            try:
                product_b_id = product_b_response.json().get('id')
            except Exception:
                product_b_id = None

        isolation_response = None
        isolation_ok = False
        if product_b_id:
            isolation_response = self.call_products_get(tenant_b['id'], token_a, product_b_id)
            isolation_ok = isolation_response.status_code in {403, 404}
            if not isolation_ok:
                self.vulnerabilities.append('Tenant A can access Tenant B data by spoofing x-tenant-id; resource server ignores tenant claim in JWT.')
        self.record('tenant_isolation', '403/404 when Tenant A accesses Tenant B data', isolation_response, isolation_ok, product_id=product_b_id)

        self.update_modules(admin_token, tenant_a['id'], user_a['id'], ['products'])
        refreshed_session = self.login(user_a['email'], user_a_password)
        refreshed_response = self.call_products_create(tenant_a['id'], refreshed_session['access_token'], 'refreshed')
        refreshed_ok = refreshed_response.status_code in {200, 201}
        self.record('user_update_flow_new_jwt', '2xx after reissuing JWT with restored products module', refreshed_response, refreshed_ok)

        invalid_token_response = self.call_products_create(tenant_a['id'], 'not-a-valid-token', 'invalid-token')
        invalid_ok = invalid_token_response.status_code == 401
        self.record('security_invalid_token', '401 unauthorized for invalid token', invalid_token_response, invalid_ok)
        if not invalid_ok:
            self.vulnerabilities.append('product-erp accepts invalid bearer tokens.')

        expired_token = self.build_expired_token(token_a)
        expired_token_response = self.call_products_create(tenant_a['id'], expired_token, 'expired-token')
        expired_ok = expired_token_response.status_code == 401
        self.record('security_expired_token', '401 unauthorized for expired token', expired_token_response, expired_ok)
        if not expired_ok:
            self.vulnerabilities.append('product-erp accepts expired JWTs.')

        missing_token_response = self.call_products_create(tenant_a['id'], None, 'missing-token')
        missing_ok = missing_token_response.status_code == 401
        self.record('security_missing_token', '401 unauthorized for missing token', missing_token_response, missing_ok)
        if not missing_ok:
            self.vulnerabilities.append('product-erp allows authenticated operations without any bearer token.')

        report = {
            'run_id': self.run_id,
            'auth_base_url': self.auth_base_url,
            'product_base_url': self.product_base_url,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'results': [asdict(item) for item in self.results],
            'vulnerabilities': sorted(set(self.vulnerabilities)),
            'summary': {
                'total': len(self.results),
                'passed': sum(1 for item in self.results if item.passed),
                'failed': sum(1 for item in self.results if not item.passed),
            },
        }
        return report


def main() -> int:
    validator = IntegrationValidator()
    try:
        report = validator.run()
    except Exception as exc:
        failure_report = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'fatal_error': str(exc),
        }
        output_dir = Path('artifacts') / 'integration'
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f'auth_product_erp_validation_failure_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json'
        output_path.write_text(json.dumps(failure_report, indent=2), encoding='utf-8')
        print(json.dumps(failure_report, indent=2))
        return 1
    finally:
        validator.close()

    output_dir = Path('artifacts') / 'integration'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'auth_product_erp_validation_{validator.run_id}.json'
    output_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['summary']['failed'] == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
