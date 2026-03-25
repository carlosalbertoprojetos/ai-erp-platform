from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import AliasChoices, BaseModel, Field, field_validator

from application.auth import decode_jwt, issue_jwt
from application.security import sanitize_email, sanitize_text
from application.settings import CoreFlowSettings
from domain.iam_models import AuthTokenResponse, AuthenticatedPrincipal, ModuleRecord, RoleRecord, SessionEnvelope, TenantRecord, UserRecord
from infrastructure.iam.repository import IamRepository


class LoginRequest(BaseModel):
    identifier: str = Field(validation_alias=AliasChoices('email', 'username', 'identifier'))
    password: str

    @field_validator('identifier', 'password')
    @classmethod
    def sanitize_fields(cls, value: str) -> str:
        return sanitize_text(value, 160)


class TenantCreateRequest(BaseModel):
    name: str
    plan: str = 'starter'
    status: str = 'active'

    @field_validator('name', 'plan', 'status')
    @classmethod
    def sanitize_fields(cls, value: str) -> str:
        return sanitize_text(value, 120)


class UserCreateRequest(BaseModel):
    name: str
    email: str
    password: str
    tenant_id: str | None = None
    is_active: bool = True
    roles: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)

    @field_validator('name', 'password')
    @classmethod
    def sanitize_text_fields(cls, value: str) -> str:
        return sanitize_text(value, 160)

    @field_validator('email')
    @classmethod
    def sanitize_email_field(cls, value: str) -> str:
        return sanitize_email(value)


class UserUpdateRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    password: str | None = None
    tenant_id: str | None = None
    is_active: bool | None = None

    @field_validator('name', 'password')
    @classmethod
    def sanitize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return sanitize_text(value, 160)

    @field_validator('email')
    @classmethod
    def sanitize_optional_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return sanitize_email(value)


class RoleAssignmentRequest(BaseModel):
    tenant_id: str | None = None
    roles: list[str] = Field(default_factory=list)


class ModuleAssignmentRequest(BaseModel):
    tenant_id: str | None = None
    modules: list[str] = Field(default_factory=list)


def build_iam_router(
    get_repository: Callable[[], IamRepository],
    get_settings: Callable[[], CoreFlowSettings],
) -> APIRouter:
    router = APIRouter(tags=['iam'])

    def resolve_principal(request: Request, authorization: str | None, settings: CoreFlowSettings) -> AuthenticatedPrincipal | None:
        principal = getattr(request.state, 'auth_principal', None)
        if isinstance(principal, AuthenticatedPrincipal):
            return principal
        token = (authorization or '').removeprefix('Bearer ').strip()
        if not token:
            return None
        principal = decode_jwt(token, settings)
        if principal is not None:
            request.state.auth_principal = principal
        return principal

    async def get_current_principal(
        request: Request,
        authorization: str | None = Header(default=None),
        settings: CoreFlowSettings = Depends(get_settings),
    ) -> AuthenticatedPrincipal:
        principal = resolve_principal(request, authorization, settings)
        if principal is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Missing or invalid bearer token.')
        return principal

    def require_admin(principal: AuthenticatedPrincipal) -> AuthenticatedPrincipal:
        if 'admin' not in principal.roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Admin role required.')
        return principal

    def get_scope_tenant(requested_tenant_id: str | None, principal: AuthenticatedPrincipal, allow_cross_tenant_for_admin: bool) -> str:
        if requested_tenant_id:
            if allow_cross_tenant_for_admin and 'admin' in principal.roles:
                return requested_tenant_id
            if requested_tenant_id != principal.tenant_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Tenant scope mismatch detected.')
            return requested_tenant_id
        return principal.tenant_id

    @router.post('/auth/login', response_model=AuthTokenResponse)
    async def login(payload: LoginRequest) -> AuthTokenResponse:
        repository = get_repository()
        user = repository.authenticate_user(payload.identifier, payload.password)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials.')
        access_token, expires_at = issue_jwt(get_settings(), user)
        return AuthTokenResponse(access_token=access_token, expires_at=expires_at, user=user)

    @router.get('/auth/session', response_model=SessionEnvelope)
    async def session(principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> SessionEnvelope:
        return SessionEnvelope(authenticated=True, principal=principal)

    @router.get('/auth/me', response_model=UserRecord)
    async def me(principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> UserRecord:
        user = get_repository().get_user(principal.tenant_id, principal.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found.')
        return user

    @router.get('/auth/access/{module_name}')
    async def module_access(module_name: str, principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> dict[str, bool | str]:
        allowed = module_name in principal.modules or 'admin' in principal.roles
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f'Module access denied: {module_name}.')
        return {'allowed': True, 'module': module_name}

    @router.get('/tenants', response_model=list[TenantRecord])
    async def list_tenants(principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> list[TenantRecord]:
        require_admin(principal)
        return get_repository().list_tenants()

    @router.post('/tenants', response_model=TenantRecord)
    async def create_tenant(payload: TenantCreateRequest, principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> TenantRecord:
        require_admin(principal)
        return get_repository().create_tenant(payload.name, payload.plan, payload.status)

    @router.get('/tenants/{tenant_id}', response_model=TenantRecord)
    async def get_tenant(tenant_id: str, principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> TenantRecord:
        scoped_tenant_id = get_scope_tenant(tenant_id, principal, allow_cross_tenant_for_admin=True)
        tenant = get_repository().get_tenant(scoped_tenant_id)
        if tenant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Tenant not found.')
        return tenant

    @router.get('/roles', response_model=list[RoleRecord])
    async def list_roles(_: AuthenticatedPrincipal = Depends(get_current_principal)) -> list[RoleRecord]:
        return get_repository().list_roles()

    @router.get('/modules', response_model=list[ModuleRecord])
    async def list_modules(_: AuthenticatedPrincipal = Depends(get_current_principal)) -> list[ModuleRecord]:
        return get_repository().list_modules()

    @router.get('/users', response_model=list[UserRecord])
    async def list_users(tenant_id: str | None = None, principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> list[UserRecord]:
        scoped_tenant_id = get_scope_tenant(tenant_id, principal, allow_cross_tenant_for_admin=True)
        return get_repository().list_users(scoped_tenant_id)

    @router.post('/users', response_model=UserRecord)
    async def create_user(payload: UserCreateRequest, principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> UserRecord:
        require_admin(principal)
        scoped_tenant_id = get_scope_tenant(payload.tenant_id, principal, allow_cross_tenant_for_admin=True)
        return get_repository().create_user(
            scoped_tenant_id,
            payload.name,
            payload.email,
            payload.password,
            payload.is_active,
            payload.roles,
            payload.modules,
        )

    @router.patch('/users/{user_id}', response_model=UserRecord)
    async def update_user(user_id: str, payload: UserUpdateRequest, principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> UserRecord:
        require_admin(principal)
        scoped_tenant_id = get_scope_tenant(payload.tenant_id, principal, allow_cross_tenant_for_admin=True)
        user = get_repository().update_user(
            scoped_tenant_id,
            user_id,
            name=payload.name,
            email=payload.email,
            password=payload.password,
            is_active=payload.is_active,
        )
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found.')
        return user

    @router.put('/users/{user_id}/roles', response_model=UserRecord)
    async def assign_roles(user_id: str, payload: RoleAssignmentRequest, principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> UserRecord:
        require_admin(principal)
        scoped_tenant_id = get_scope_tenant(payload.tenant_id, principal, allow_cross_tenant_for_admin=True)
        user = get_repository().assign_roles(scoped_tenant_id, user_id, payload.roles)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found.')
        return user

    @router.put('/users/{user_id}/modules', response_model=UserRecord)
    async def assign_modules(user_id: str, payload: ModuleAssignmentRequest, principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> UserRecord:
        require_admin(principal)
        scoped_tenant_id = get_scope_tenant(payload.tenant_id, principal, allow_cross_tenant_for_admin=True)
        user = get_repository().assign_modules(scoped_tenant_id, user_id, payload.modules)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found.')
        return user

    return router
