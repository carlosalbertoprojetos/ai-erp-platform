from __future__ import annotations

import asyncio

from agents.base import BaseAgent
from domain.models import AgentResult, AgentStatus, ArchitecturePlan, ExecutionContext


class BackendAgent(BaseAgent):
    name = "backend"
    required_state_keys = ("architect",)

    def __init__(self, logger, code_generation_engine, file_manager):
        super().__init__(logger)
        self.code_generation_engine = code_generation_engine
        self.file_manager = file_manager

    async def _execute(self, context: ExecutionContext) -> AgentResult:
        plan = ArchitecturePlan.model_validate(context.state["architect"]["architecture"])
        project = self.code_generation_engine.generate(plan, context.target_root)
        write_result = await asyncio.to_thread(self.file_manager.apply, project.root_path, project.files, context.dry_run)
        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.SUCCESS,
            payload={
                "project_root": project.root_path,
                "written_files": write_result.written_files,
                "created_files": write_result.created_files,
                "updated_files": write_result.updated_files,
                "unchanged_files": write_result.unchanged_files,
                "dry_run": context.dry_run,
            },
            artifacts=project.files,
        )
