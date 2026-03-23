from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from domain.models import AgentLogEntry, ExecutionContext, ExecutionStatusResponse, ExecutionSummary, FileArtifact
from infrastructure.database.models import ArtifactModel, Base, ExecutionLogModel, ExecutionModel


class ExecutionRepository:
    def __init__(self, database_url: str = "sqlite:///./.coreflow/coreflow.db"):
        self.database_url = database_url
        if database_url.startswith("sqlite:///"):
            database_path = Path(database_url.replace("sqlite:///", "", 1))
            database_path.parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, future=True, connect_args=connect_args, pool_pre_ping=True)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, class_=Session)

    def ensure_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def create_execution(self, context: ExecutionContext, pipeline_name: str, status: str = "running") -> str:
        with self.session_factory() as session:
            existing = session.execute(
                select(ExecutionModel).where(ExecutionModel.correlation_id == context.correlation_id)
            ).scalar_one_or_none()
            if existing is not None:
                existing.pipeline_name = pipeline_name
                existing.status = status
                existing.request_payload = context.request.model_dump(mode="json")
                session.commit()
                return existing.id

            record = ExecutionModel(
                correlation_id=context.correlation_id,
                pipeline_name=pipeline_name,
                status=status,
                request_payload=context.request.model_dump(mode="json"),
            )
            session.add(record)
            session.commit()
            return record.id

    def append_logs(self, execution_id: str, logs: list[AgentLogEntry]) -> None:
        if not logs:
            return
        with self.session_factory() as session:
            session.add_all(
                [
                    ExecutionLogModel(
                        execution_id=execution_id,
                        correlation_id=log.correlation_id,
                        agent_name=log.agent_name,
                        level=log.level,
                        message=log.message,
                        payload=log.payload,
                    )
                    for log in logs
                ]
            )
            session.commit()

    def append_artifacts(self, execution_id: str, agent_name: str, artifacts: list[FileArtifact]) -> None:
        if not artifacts:
            return
        with self.session_factory() as session:
            session.add_all(
                [
                    ArtifactModel(
                        execution_id=execution_id,
                        agent_name=agent_name,
                        path=artifact.path,
                        operation=artifact.operation.value,
                        content=artifact.content,
                    )
                    for artifact in artifacts
                ]
            )
            session.commit()

    def complete_execution(self, execution_id: str, summary: ExecutionSummary) -> None:
        with self.session_factory() as session:
            record = session.get(ExecutionModel, execution_id)
            if record is None:
                return
            record.status = summary.status.value
            record.summary_payload = summary.model_dump(mode="json")
            session.commit()

    def get_execution_status(self, correlation_id: str) -> ExecutionStatusResponse | None:
        with self.session_factory() as session:
            statement = select(ExecutionModel).where(ExecutionModel.correlation_id == correlation_id)
            record = session.execute(statement).scalar_one_or_none()
            if record is None:
                return None
            summary = None
            if record.summary_payload:
                summary = ExecutionSummary.model_validate(record.summary_payload)
            return ExecutionStatusResponse(correlation_id=correlation_id, status=record.status, summary=summary)

    def healthcheck(self) -> bool:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
