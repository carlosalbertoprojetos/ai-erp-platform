from __future__ import annotations

from agents.base import BaseAgent
from domain.models import AgentResult, AgentStatus, ArchitecturePlan, ExecutionContext
from shared.llm.provider import LLMRequest


class ArchitectAgent(BaseAgent):
    name = "architect"

    def __init__(self, logger, llm_service, architecture_service):
        super().__init__(logger)
        self.llm_service = llm_service
        self.architecture_service = architecture_service

    async def _execute(self, context: ExecutionContext) -> AgentResult:
        fallback_plan = self.architecture_service.design(context.request)
        response = await self.llm_service.generate(
            LLMRequest(
                instructions="Design a DDD + Clean Architecture blueprint and keep the output strictly valid JSON.",
                prompt=context.request.model_dump_json(indent=2),
                metadata={"template_output": fallback_plan.model_dump(mode="json")},
                timeout_seconds=30.0,
            ),
            ArchitecturePlan,
            fallback=fallback_plan,
        )
        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.SUCCESS,
            payload={"architecture": response.model_dump(mode="json")},
        )
