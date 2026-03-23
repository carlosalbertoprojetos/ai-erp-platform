from __future__ import annotations

import asyncio
from pathlib import Path

from agents.base import BaseAgent
from domain.models import AgentResult, AgentStatus, ExecutionContext, SecurityReport


class SecurityAgent(BaseAgent):
    name = "security"
    required_state_keys = ("backend",)

    def __init__(self, logger, security_scanner):
        super().__init__(logger)
        self.security_scanner = security_scanner

    async def _execute(self, context: ExecutionContext) -> AgentResult:
        if context.dry_run:
            report = SecurityReport(status="passed", checks=["Dry-run mode skipped filesystem scan."], findings=[])
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.SUCCESS,
                payload={"security_report": report.model_dump(mode="json")},
            )

        project_root = Path(context.state["backend"]["project_root"])
        report = await asyncio.to_thread(self.security_scanner.scan, project_root)
        status = AgentStatus.SUCCESS if report.status == "passed" else AgentStatus.ERROR
        return AgentResult(
            agent_name=self.name,
            status=status,
            payload={"security_report": report.model_dump(mode="json")},
            errors=[item.title for item in report.findings if item.severity == "high"],
        )
