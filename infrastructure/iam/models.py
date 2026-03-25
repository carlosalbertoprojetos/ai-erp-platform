from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.models import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantModel(Base):
    __tablename__ = 'tenants'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(200), unique=True)
    plan: Mapped[str] = mapped_column(String(64), default='starter')
    status: Mapped[str] = mapped_column(String(32), default='active')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    users: Mapped[list['UserModel']] = relationship('infrastructure.iam.models.UserModel', back_populates='tenant', cascade='all, delete-orphan')


class UserModel(Base):
    __tablename__ = 'users'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    tenant: Mapped[TenantModel] = relationship('infrastructure.iam.models.TenantModel', back_populates='users')
    role_links: Mapped[list['UserRoleModel']] = relationship('infrastructure.iam.models.UserRoleModel', back_populates='user', cascade='all, delete-orphan')
    module_links: Mapped[list['UserModuleModel']] = relationship('infrastructure.iam.models.UserModuleModel', back_populates='user', cascade='all, delete-orphan')


class ModuleModel(Base):
    __tablename__ = 'modules'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)

    user_links: Mapped[list['UserModuleModel']] = relationship('infrastructure.iam.models.UserModuleModel', back_populates='module', cascade='all, delete-orphan')


class UserModuleModel(Base):
    __tablename__ = 'user_modules'
    __table_args__ = (UniqueConstraint('user_id', 'module_id', name='uq_user_module'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    module_id: Mapped[str] = mapped_column(ForeignKey('modules.id'), index=True)

    user: Mapped[UserModel] = relationship('infrastructure.iam.models.UserModel', back_populates='module_links')
    module: Mapped[ModuleModel] = relationship('infrastructure.iam.models.ModuleModel', back_populates='user_links')


class RoleModel(Base):
    __tablename__ = 'roles'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)

    user_links: Mapped[list['UserRoleModel']] = relationship('infrastructure.iam.models.UserRoleModel', back_populates='role', cascade='all, delete-orphan')


class UserRoleModel(Base):
    __tablename__ = 'user_roles'
    __table_args__ = (UniqueConstraint('user_id', 'role_id', name='uq_user_role'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    role_id: Mapped[str] = mapped_column(ForeignKey('roles.id'), index=True)

    user: Mapped[UserModel] = relationship('infrastructure.iam.models.UserModel', back_populates='role_links')
    role: Mapped[RoleModel] = relationship('infrastructure.iam.models.RoleModel', back_populates='user_links')
