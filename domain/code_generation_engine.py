from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from domain.models import ArchitecturePlan, FileArtifact, GeneratedProject
from domain.services import slugify


class FastAPICodeGenerationEngine:
    def generate(self, plan: ArchitecturePlan, target_root: str) -> GeneratedProject:
        module = plan.modules[0]
        module_name = slugify(module.name)
        entity_name = module.entities[0]
        feature_root = Path(target_root) / module_name / "backend"
        api_prefix = plan.feature.api_prefix.rstrip("/")

        files = [
            FileArtifact(path="app/__init__.py", content=""),
            FileArtifact(path="app/domain/__init__.py", content=""),
            FileArtifact(path="app/application/__init__.py", content=""),
            FileArtifact(path="app/infrastructure/__init__.py", content=""),
            FileArtifact(path="app/presentation/__init__.py", content=""),
            FileArtifact(path="app/security/__init__.py", content=""),
            FileArtifact(path="app/domain/entities.py", content=self._entities_py(entity_name)),
            FileArtifact(path="app/domain/repositories.py", content=self._repositories_py(entity_name)),
            FileArtifact(path="app/application/use_cases.py", content=self._use_cases_py(entity_name)),
            FileArtifact(path="app/infrastructure/repository.py", content=self._repository_py(entity_name)),
            FileArtifact(path="app/security/auth.py", content=self._auth_py()),
            FileArtifact(path="app/presentation/api.py", content=self._api_py(api_prefix, module_name, entity_name)),
            FileArtifact(path="app/main.py", content=self._main_py()),
            FileArtifact(path="README.md", content=self._readme_md(plan, module_name)),
            FileArtifact(path="pyproject.toml", content=self._pyproject_toml(module_name)),
        ]
        return GeneratedProject(root_path=str(feature_root), files=files)

    def _entities_py(self, entity_name: str) -> str:
        return dedent(
            f"""
            from pydantic import BaseModel, Field


            class {entity_name}(BaseModel):
                id: int | None = None
                name: str = Field(min_length=3, max_length=120)
                description: str = Field(default="", max_length=500)


            class {entity_name}Create(BaseModel):
                name: str = Field(min_length=3, max_length=120)
                description: str = Field(default="", max_length=500)
            """
        ).strip() + "\n"

    def _repositories_py(self, entity_name: str) -> str:
        return dedent(
            f"""
            from typing import Protocol

            from app.domain.entities import {entity_name}, {entity_name}Create


            class {entity_name}Repository(Protocol):
                def add(self, payload: {entity_name}Create) -> {entity_name}:
                    ...

                def list_all(self) -> list[{entity_name}]:
                    ...
            """
        ).strip() + "\n"

    def _use_cases_py(self, entity_name: str) -> str:
        return dedent(
            f"""
            from app.domain.entities import {entity_name}, {entity_name}Create
            from app.domain.repositories import {entity_name}Repository


            class Create{entity_name}UseCase:
                def __init__(self, repository: {entity_name}Repository):
                    self._repository = repository

                def execute(self, payload: {entity_name}Create) -> {entity_name}:
                    return self._repository.add(payload)


            class List{entity_name}UseCase:
                def __init__(self, repository: {entity_name}Repository):
                    self._repository = repository

                def execute(self) -> list[{entity_name}]:
                    return self._repository.list_all()
            """
        ).strip() + "\n"

    def _repository_py(self, entity_name: str) -> str:
        return dedent(
            f"""
            from app.domain.entities import {entity_name}, {entity_name}Create


            class InMemoryRepository:
                def __init__(self):
                    self._items: list[{entity_name}] = []
                    self._sequence = 1

                def add(self, payload: {entity_name}Create) -> {entity_name}:
                    entity = {entity_name}(id=self._sequence, **payload.model_dump())
                    self._items.append(entity)
                    self._sequence += 1
                    return entity

                def list_all(self) -> list[{entity_name}]:
                    return list(self._items)
            """
        ).strip() + "\n"

    def _auth_py(self) -> str:
        return dedent(
            """
            import os

            from fastapi import Header, HTTPException, status


            def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
                expected_token = os.getenv("COREFLOW_API_TOKEN", "local-token")
                expected_header = f"Bearer {expected_token}"
                if authorization != expected_header:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Missing or invalid bearer token.",
                    )
                return expected_token
            """
        ).strip() + "\n"

    def _api_py(self, api_prefix: str, module_name: str, entity_name: str) -> str:
        return dedent(
            f"""
            from fastapi import APIRouter, Depends

            from app.application.use_cases import Create{entity_name}UseCase, List{entity_name}UseCase
            from app.domain.entities import {entity_name}, {entity_name}Create
            from app.infrastructure.repository import InMemoryRepository
            from app.security.auth import get_bearer_token

            router = APIRouter(prefix="{api_prefix}/{module_name}", tags=["{module_name}"])
            repository = InMemoryRepository()


            def _create_use_case() -> Create{entity_name}UseCase:
                return Create{entity_name}UseCase(repository)


            def _list_use_case() -> List{entity_name}UseCase:
                return List{entity_name}UseCase(repository)


            @router.get("/health")
            def healthcheck() -> dict[str, str]:
                return {{"status": "ok", "service": "{module_name}"}}


            @router.post("", response_model={entity_name})
            def create_item(
                payload: {entity_name}Create,
                _: str = Depends(get_bearer_token),
            ) -> {entity_name}:
                return _create_use_case().execute(payload)


            @router.get("", response_model=list[{entity_name}])
            def list_items(_: str = Depends(get_bearer_token)) -> list[{entity_name}]:
                return _list_use_case().execute()
            """
        ).strip() + "\n"

    def _main_py(self) -> str:
        return dedent(
            """
            from fastapi import FastAPI

            from app.presentation.api import router

            app = FastAPI(title="CoreFlow Generated Service")
            app.include_router(router)


            @app.get("/health")
            def healthcheck() -> dict[str, str]:
                return {"status": "ok"}
            """
        ).strip() + "\n"

    def _readme_md(self, plan: ArchitecturePlan, module_name: str) -> str:
        policies = "\n".join(f"- {policy}" for policy in plan.policies)
        return dedent(
            f"""
            # {plan.feature.title}

            Generated by CoreFlow Agents.

            ## Module

            - `{module_name}`

            ## Policies

            {policies}
            """
        ).strip() + "\n"

    def _pyproject_toml(self, module_name: str) -> str:
        return dedent(
            f"""
            [project]
            name = "{module_name}-service"
            version = "0.1.0"
            requires-python = ">=3.12"
            dependencies = [
                "fastapi>=0.115.0",
                "uvicorn>=0.30.0",
                "pydantic>=2.9.0",
            ]

            [tool.pytest.ini_options]
            pythonpath = ["."]
            addopts = "-q"
            """
        ).strip() + "\n"
