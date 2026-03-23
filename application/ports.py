from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.models import AgentResult, ExecutionContext, ExecutionStatusResponse, ExecutionSummary, PipelineDefinition


@runtime_checkable
class AgentPort(Protocol):
    name: str

    async def execute(self, context: ExecutionContext) -> AgentResult:
        ...


class PipelineLoaderPort(Protocol):
    def load(self, name: str) -> PipelineDefinition:
        ...


class ExecutionRepositoryPort(Protocol):
    def ensure_schema(self) -> None:
        ...

    def create_execution(self, context: ExecutionContext, pipeline_name: str, status: str = "running") -> str:
        ...

    def append_logs(self, execution_id: str, logs: list) -> None:
        ...

    def append_artifacts(self, execution_id: str, agent_name: str, artifacts: list) -> None:
        ...

    def complete_execution(self, execution_id: str, summary: ExecutionSummary) -> None:
        ...

    def get_execution_status(self, correlation_id: str) -> ExecutionStatusResponse | None:
        ...
