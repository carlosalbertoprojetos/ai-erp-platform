from __future__ import annotations

import asyncio
from pathlib import Path

from agents.base import BaseAgent
from domain.models import AgentResult, AgentStatus, ExecutionContext


class RefactorAgent(BaseAgent):
    name = "refactor"
    required_state_keys = ("backend",)

    def __init__(self, logger, refactor_analyzer):
        super().__init__(logger)
        self.refactor_analyzer = refactor_analyzer

    async def _execute(self, context: ExecutionContext) -> AgentResult:
        project_root = Path(context.state["backend"]["project_root"])
        report = await asyncio.to_thread(self.refactor_analyzer.analyze, project_root)
        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.SUCCESS,
            payload={"refactor_report": report.model_dump(mode="json")},
        )
