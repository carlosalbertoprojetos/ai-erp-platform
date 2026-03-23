from __future__ import annotations

from abc import ABC, abstractmethod

from domain.exceptions import AgentValidationError
from domain.models import AgentLogEntry, AgentResult, AgentStatus, ExecutionContext


class BaseAgent(ABC):
    name: str = "base"
    required_state_keys: tuple[str, ...] = ()

    def __init__(self, logger):
        self.logger = logger

    async def execute(self, context: ExecutionContext) -> AgentResult:
        collected_logs: list[AgentLogEntry] = []
        self._log(collected_logs, context, "info", "Agent execution started.")
        try:
            self.validate_context(context)
            await self.before_execute(context, collected_logs)
            result = await self._execute(context)
            await self.after_execute(context, result, collected_logs)
            result.logs = collected_logs + result.logs
            result.status = AgentStatus(result.status)
            return AgentResult.model_validate(result.model_dump(mode="json"))
        except Exception as exc:
            self._log(collected_logs, context, "error", "Agent execution failed.", {"error": str(exc)})
            await self.on_error(context, exc, collected_logs)
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.ERROR,
                errors=[str(exc)],
                logs=collected_logs,
            )

    def validate_context(self, context: ExecutionContext) -> None:
        missing = [key for key in self.required_state_keys if key not in context.state]
        if missing:
            raise AgentValidationError(f"Missing required state for {self.name}: {missing}")

    async def before_execute(self, context: ExecutionContext, logs: list[AgentLogEntry]) -> None:
        self._log(logs, context, "info", "Validation complete.")

    async def after_execute(self, context: ExecutionContext, result: AgentResult, logs: list[AgentLogEntry]) -> None:
        self._log(logs, context, "info", "Agent execution finished.", {"status": result.status.value})

    async def on_error(self, context: ExecutionContext, exc: Exception, logs: list[AgentLogEntry]) -> None:
        return None

    def _log(
        self,
        logs: list[AgentLogEntry],
        context: ExecutionContext,
        level: str,
        message: str,
        payload: dict | None = None,
    ) -> AgentLogEntry:
        entry = self.logger.log(context.correlation_id, self.name, level, message, payload)
        logs.append(entry)
        return entry

    @abstractmethod
    async def _execute(self, context: ExecutionContext) -> AgentResult:
        raise NotImplementedError
