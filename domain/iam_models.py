from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantRecord(BaseModel):
    id: str
    name: str
    plan: str
    status: str
    created_at: datetime = Field(default_factory=utc_now)


class ModuleRecord(BaseModel):
    id: str
    name: str


class RoleRecord(BaseModel):
    id: str
    name: str


class UserRecord(BaseModel):
    id: str
    name: str
    email: str
    tenant_id: str
    is_active: bool
    created_at: datetime = Field(default_factory=utc_now)
    roles: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)


class AuthenticatedPrincipal(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    name: str
    roles: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    exp: datetime


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    expires_at: datetime
    user: UserRecord


class SessionEnvelope(BaseModel):
    authenticated: bool
    principal: AuthenticatedPrincipal | None = None
