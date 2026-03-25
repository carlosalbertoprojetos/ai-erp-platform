from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from application.settings import CoreFlowSettings
from domain.iam_models import AuthenticatedPrincipal, UserRecord


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except ValueError:
        return False


def issue_jwt(settings: CoreFlowSettings, user: UserRecord) -> tuple[str, datetime]:
    issued_at = utc_now()
    expires_at = issued_at + timedelta(seconds=settings.auth_token_ttl_seconds)
    payload = {
        'sub': user.id,
        'tenant_id': user.tenant_id,
        'email': user.email,
        'name': user.name,
        'roles': user.roles,
        'modules': user.modules,
        'iat': int(issued_at.timestamp()),
        'exp': int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.auth_secret, algorithm='HS256')
    return token, expires_at


def decode_jwt(token: str, settings: CoreFlowSettings) -> AuthenticatedPrincipal | None:
    try:
        payload = jwt.decode(token, settings.auth_secret, algorithms=['HS256'])
    except jwt.PyJWTError:
        return None

    exp_value = payload.get('exp')
    if exp_value is None:
        return None
    try:
        exp = datetime.fromtimestamp(int(exp_value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None

    subject = str(payload.get('sub') or '').strip()
    tenant_id = str(payload.get('tenant_id') or '').strip()
    email = str(payload.get('email') or '').strip()
    name = str(payload.get('name') or '').strip()
    roles = [str(item) for item in payload.get('roles', [])]
    modules = [str(item) for item in payload.get('modules', [])]
    if not subject or not tenant_id:
        return None
    return AuthenticatedPrincipal(
        user_id=subject,
        tenant_id=tenant_id,
        email=email,
        name=name,
        roles=roles,
        modules=modules,
        exp=exp,
    )
