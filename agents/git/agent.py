from __future__ import annotations

import asyncio
from pathlib import Path

from agents.base import BaseAgent
from domain.models import AgentResult, AgentStatus, ExecutionContext


class GitAgent(BaseAgent):
    name = "git"
    required_state_keys = ("backend",)

    def __init__(self, logger, git_service):
        super().__init__(logger)
        self.git_service = git_service

    async def _execute(self, context: ExecutionContext) -> AgentResult:
        project_root = Path(context.state["backend"]["project_root"])
        result = await asyncio.to_thread(
            self.git_service.apply,
            project_root,
            context.git,
            context.correlation_id,
        )
        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.SUCCESS,
            payload={"git_result": result},
        )
