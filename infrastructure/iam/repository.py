from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, func, or_, select, text
from sqlalchemy.orm import Session, joinedload, sessionmaker

from application.auth import hash_password, verify_password
from domain.iam_models import ModuleRecord, RoleRecord, TenantRecord, UserRecord
from infrastructure.database.models import Base
from infrastructure.iam.models import ModuleModel, RoleModel, TenantModel, UserModel, UserModuleModel, UserRoleModel


class IamRepository:
    def __init__(self, database_url: str = 'sqlite:///./.coreflow/coreflow.db'):
        self.database_url = database_url
        if database_url.startswith('sqlite:///'):
            database_path = Path(database_url.replace('sqlite:///', '', 1))
            database_path.parent.mkdir(parents=True, exist_ok=True)
        connect_args = {'check_same_thread': False} if database_url.startswith('sqlite') else {}
        self.engine = create_engine(database_url, future=True, connect_args=connect_args, pool_pre_ping=True)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, class_=Session)

    def ensure_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def healthcheck(self) -> bool:
        with self.engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return True

    def seed_defaults(
        self,
        tenant_name: str,
        plan: str,
        status: str,
        admin_name: str,
        admin_email: str,
        admin_password: str,
    ) -> tuple[TenantRecord, UserRecord]:
        with self.session_factory() as session:
            self._seed_roles(session)
            self._seed_modules(session)

            tenant = session.execute(
                select(TenantModel).where(func.lower(TenantModel.name) == tenant_name.lower())
            ).scalar_one_or_none()
            if tenant is None:
                tenant = TenantModel(name=tenant_name, plan=plan, status=status)
                session.add(tenant)
                session.flush()

            admin_user = session.execute(
                select(UserModel)
                .options(
                    joinedload(UserModel.role_links).joinedload(UserRoleModel.role),
                    joinedload(UserModel.module_links).joinedload(UserModuleModel.module),
                )
                .where(func.lower(UserModel.email) == admin_email.lower())
            ).unique().scalar_one_or_none()
            if admin_user is None:
                admin_user = UserModel(
                    name=admin_name,
                    email=admin_email.lower(),
                    password_hash=hash_password(admin_password),
                    tenant_id=tenant.id,
                    is_active=True,
                )
                session.add(admin_user)
                session.flush()

            all_modules = session.execute(select(ModuleModel).order_by(ModuleModel.name)).scalars().all()
            self._replace_user_roles(session, admin_user, ['admin'])
            self._replace_user_modules(session, admin_user, [item.name for item in all_modules])
            session.commit()
            return self._to_tenant_record(tenant), self._to_user_record(admin_user)

    def authenticate_user(self, identifier: str, password: str) -> UserRecord | None:
        with self.session_factory() as session:
            user = session.execute(
                select(UserModel)
                .options(
                    joinedload(UserModel.role_links).joinedload(UserRoleModel.role),
                    joinedload(UserModel.module_links).joinedload(UserModuleModel.module),
                )
                .where(
                    or_(
                        func.lower(UserModel.email) == identifier.lower(),
                        func.lower(UserModel.name) == identifier.lower(),
                    )
                )
            ).unique().scalar_one_or_none()
            if user is None or not user.is_active:
                return None
            if not verify_password(password, user.password_hash):
                return None
            return self._to_user_record(user)

    def list_tenants(self) -> list[TenantRecord]:
        with self.session_factory() as session:
            tenants = session.execute(select(TenantModel).order_by(TenantModel.created_at)).scalars().all()
            return [self._to_tenant_record(item) for item in tenants]

    def create_tenant(self, name: str, plan: str, status: str = 'active') -> TenantRecord:
        with self.session_factory() as session:
            existing = session.execute(
                select(TenantModel).where(func.lower(TenantModel.name) == name.lower())
            ).scalar_one_or_none()
            if existing is not None:
                raise ValueError('A tenant with this name already exists.')
            tenant = TenantModel(name=name, plan=plan, status=status)
            session.add(tenant)
            session.commit()
            return self._to_tenant_record(tenant)

    def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        with self.session_factory() as session:
            tenant = session.get(TenantModel, tenant_id)
            if tenant is None:
                return None
            return self._to_tenant_record(tenant)

    def list_roles(self) -> list[RoleRecord]:
        with self.session_factory() as session:
            roles = session.execute(select(RoleModel).order_by(RoleModel.name)).scalars().all()
            return [RoleRecord(id=item.id, name=item.name) for item in roles]

    def list_modules(self) -> list[ModuleRecord]:
        with self.session_factory() as session:
            modules = session.execute(select(ModuleModel).order_by(ModuleModel.name)).scalars().all()
            return [ModuleRecord(id=item.id, name=item.name) for item in modules]

    def list_users(self, tenant_id: str) -> list[UserRecord]:
        with self.session_factory() as session:
            users = session.execute(
                select(UserModel)
                .options(
                    joinedload(UserModel.role_links).joinedload(UserRoleModel.role),
                    joinedload(UserModel.module_links).joinedload(UserModuleModel.module),
                )
                .where(UserModel.tenant_id == tenant_id)
                .order_by(UserModel.created_at)
            ).unique().scalars().all()
            return [self._to_user_record(item) for item in users]

    def get_user(self, tenant_id: str, user_id: str) -> UserRecord | None:
        with self.session_factory() as session:
            user = session.execute(
                select(UserModel)
                .options(
                    joinedload(UserModel.role_links).joinedload(UserRoleModel.role),
                    joinedload(UserModel.module_links).joinedload(UserModuleModel.module),
                )
                .where(UserModel.id == user_id, UserModel.tenant_id == tenant_id)
            ).unique().scalar_one_or_none()
            if user is None:
                return None
            return self._to_user_record(user)

    def create_user(
        self,
        tenant_id: str,
        name: str,
        email: str,
        password: str,
        is_active: bool,
        roles: list[str],
        modules: list[str],
    ) -> UserRecord:
        with self.session_factory() as session:
            tenant = session.get(TenantModel, tenant_id)
            if tenant is None:
                raise ValueError('Tenant not found.')
            existing = session.execute(
                select(UserModel).where(func.lower(UserModel.email) == email.lower())
            ).scalar_one_or_none()
            if existing is not None:
                raise ValueError('A user with this email already exists.')
            user = UserModel(
                name=name,
                email=email.lower(),
                password_hash=hash_password(password),
                tenant_id=tenant_id,
                is_active=is_active,
            )
            session.add(user)
            session.flush()
            self._replace_user_roles(session, user, roles)
            self._replace_user_modules(session, user, modules)
            session.commit()
            return self.get_user(tenant_id, user.id) or self._to_user_record(user)

    def update_user(
        self,
        tenant_id: str,
        user_id: str,
        name: str | None = None,
        email: str | None = None,
        password: str | None = None,
        is_active: bool | None = None,
    ) -> UserRecord | None:
        with self.session_factory() as session:
            user = session.execute(
                select(UserModel)
                .options(
                    joinedload(UserModel.role_links).joinedload(UserRoleModel.role),
                    joinedload(UserModel.module_links).joinedload(UserModuleModel.module),
                )
                .where(UserModel.id == user_id, UserModel.tenant_id == tenant_id)
            ).unique().scalar_one_or_none()
            if user is None:
                return None
            if email and email.lower() != user.email.lower():
                existing = session.execute(
                    select(UserModel).where(func.lower(UserModel.email) == email.lower())
                ).scalar_one_or_none()
                if existing is not None:
                    raise ValueError('A user with this email already exists.')
                user.email = email.lower()
            if name is not None:
                user.name = name
            if password:
                user.password_hash = hash_password(password)
            if is_active is not None:
                user.is_active = is_active
            session.commit()
            return self._to_user_record(user)

    def assign_roles(self, tenant_id: str, user_id: str, role_names: list[str]) -> UserRecord | None:
        with self.session_factory() as session:
            user = session.execute(
                select(UserModel)
                .options(
                    joinedload(UserModel.role_links).joinedload(UserRoleModel.role),
                    joinedload(UserModel.module_links).joinedload(UserModuleModel.module),
                )
                .where(UserModel.id == user_id, UserModel.tenant_id == tenant_id)
            ).unique().scalar_one_or_none()
            if user is None:
                return None
            self._replace_user_roles(session, user, role_names)
            session.commit()
            return self._to_user_record(user)

    def assign_modules(self, tenant_id: str, user_id: str, module_names: list[str]) -> UserRecord | None:
        with self.session_factory() as session:
            user = session.execute(
                select(UserModel)
                .options(
                    joinedload(UserModel.role_links).joinedload(UserRoleModel.role),
                    joinedload(UserModel.module_links).joinedload(UserModuleModel.module),
                )
                .where(UserModel.id == user_id, UserModel.tenant_id == tenant_id)
            ).unique().scalar_one_or_none()
            if user is None:
                return None
            self._replace_user_modules(session, user, module_names)
            session.commit()
            return self._to_user_record(user)

    def _seed_roles(self, session: Session) -> None:
        if session.scalar(select(func.count()).select_from(RoleModel)):
            return
        session.add_all([RoleModel(name='admin'), RoleModel(name='manager'), RoleModel(name='user')])

    def _seed_modules(self, session: Session) -> None:
        if session.scalar(select(func.count()).select_from(ModuleModel)):
            return
        session.add_all(
            [
                ModuleModel(name='products'),
                ModuleModel(name='crm'),
                ModuleModel(name='sales'),
                ModuleModel(name='finance'),
            ]
        )

    def _replace_user_roles(self, session: Session, user: UserModel, role_names: list[str]) -> None:
        normalized = self._normalize_names(role_names)
        roles = session.execute(select(RoleModel).where(RoleModel.name.in_(normalized))).scalars().all() if normalized else []
        if len(roles) != len(normalized):
            missing = sorted(set(normalized) - {item.name for item in roles})
            raise ValueError(f'Unknown roles: {", ".join(missing)}')
        user.role_links.clear()
        session.flush()
        for role in roles:
            user.role_links.append(UserRoleModel(role_id=role.id))

    def _replace_user_modules(self, session: Session, user: UserModel, module_names: list[str]) -> None:
        normalized = self._normalize_names(module_names)
        modules = session.execute(select(ModuleModel).where(ModuleModel.name.in_(normalized))).scalars().all() if normalized else []
        if len(modules) != len(normalized):
            missing = sorted(set(normalized) - {item.name for item in modules})
            raise ValueError(f'Unknown modules: {", ".join(missing)}')
        user.module_links.clear()
        session.flush()
        for module in modules:
            user.module_links.append(UserModuleModel(module_id=module.id))

    def _normalize_names(self, values: list[str]) -> list[str]:
        return sorted({item.strip().lower() for item in values if item and item.strip()})

    def _to_tenant_record(self, item: TenantModel) -> TenantRecord:
        return TenantRecord(id=item.id, name=item.name, plan=item.plan, status=item.status, created_at=item.created_at)

    def _to_user_record(self, item: UserModel) -> UserRecord:
        return UserRecord(
            id=item.id,
            name=item.name,
            email=item.email,
            tenant_id=item.tenant_id,
            is_active=item.is_active,
            created_at=item.created_at,
            roles=sorted(link.role.name for link in item.role_links if link.role is not None),
            modules=sorted(link.module.name for link in item.module_links if link.module is not None),
        )
