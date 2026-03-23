from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine

from domain.models import AgentLogEntry, ExecutionContext, ExecutionSummary, FeatureRequest, FileArtifact, GitOperationResult
from infrastructure.database.models import Base
from infrastructure.database.repository import ExecutionRepository


def test_repository_persists_execution_summary_and_status_lookup(tmp_path: Path):
    database_path = tmp_path / "executions.db"
    repository = ExecutionRepository(f"sqlite:///{database_path}")
    repository.ensure_schema()

    context = ExecutionContext(
        request=FeatureRequest(title="Finance", description="Track expenses"),
        target_root=str(tmp_path),
        correlation_id="corr-123",
    )
    execution_id = repository.create_execution(context, "default", "queued")
    queued_status = repository.get_execution_status("corr-123")
    assert queued_status is not None
    assert queued_status.status == "queued"

    repository.append_logs(
        execution_id,
        [
            AgentLogEntry(
                correlation_id=context.correlation_id,
                agent_name="architect",
                level="info",
                message="done",
            )
        ],
    )
    repository.append_artifacts(
        execution_id,
        "backend",
        [FileArtifact(path="app/main.py", content="print('ok')")],
    )
    summary = ExecutionSummary(
        correlation_id=context.correlation_id,
        status="success",
        pipeline="default",
        request=context.request,
        results={},
        artifacts_root=str(tmp_path),
        logs=[],
        git=GitOperationResult(performed=False, reason="disabled"),
    )
    repository.complete_execution(execution_id, summary)

    status = repository.get_execution_status("corr-123")
    assert status is not None
    assert status.status == "success"
    assert status.summary is not None
    assert repository.healthcheck() is True

    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        rows = list(connection.exec_driver_sql("SELECT status FROM executions"))
    assert rows[0][0] == "success"
