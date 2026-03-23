from __future__ import annotations

from domain.models import AgentResult, AgentStatus, ExecutionContext, FeatureRequest
from shared.observability.logger import JsonExecutionLogger

from agents.base import BaseAgent


class SuccessAgent(BaseAgent):
    name = "success"

    async def _execute(self, context: ExecutionContext) -> AgentResult:
        return AgentResult(agent_name=self.name, status=AgentStatus.SUCCESS, payload={"ok": True})


class FailingAgent(BaseAgent):
    name = "failing"

    async def _execute(self, context: ExecutionContext) -> AgentResult:
        raise RuntimeError("boom")


async def test_base_agent_returns_successful_result(tmp_path):
    agent = SuccessAgent(JsonExecutionLogger(root_path=str(tmp_path)))
    context = ExecutionContext(request=FeatureRequest(title="A", description="B"), target_root=str(tmp_path))

    result = await agent.execute(context)

    assert result.status == AgentStatus.SUCCESS
    assert result.payload["ok"] is True


async def test_base_agent_wraps_failures(tmp_path):
    agent = FailingAgent(JsonExecutionLogger(root_path=str(tmp_path)))
    context = ExecutionContext(request=FeatureRequest(title="A", description="B"), target_root=str(tmp_path))

    result = await agent.execute(context)

    assert result.status == AgentStatus.ERROR
    assert result.errors == ["boom"]
    assert any(log.level == "error" for log in result.logs)
