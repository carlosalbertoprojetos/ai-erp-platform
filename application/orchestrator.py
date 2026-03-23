from __future__ import annotations

import asyncio
from uuid import uuid4

from application.ports import AgentPort, ExecutionRepositoryPort, PipelineLoaderPort
from domain.models import AgentResult, AgentStatus, ExecutionContext, ExecutionSummary, PipelineDefinition, PipelineStep, RunRequest


class AgentOrchestrator:
    def __init__(
        self,
        agents: dict[str, AgentPort],
        pipeline_loader: PipelineLoaderPort,
        execution_repository: ExecutionRepositoryPort,
    ):
        self.agents = agents
        self.pipeline_loader = pipeline_loader
        self.execution_repository = execution_repository

    async def run(self, request: RunRequest) -> ExecutionSummary:
        pipeline: PipelineDefinition = self.pipeline_loader.load(request.pipeline_name)
        context = ExecutionContext(
            correlation_id=request.correlation_id or str(uuid4()),
            request=request.request,
            target_root=request.target_root,
            dry_run=request.dry_run,
            git=request.git,
        )
        await asyncio.to_thread(self.execution_repository.ensure_schema)
        execution_id = await asyncio.to_thread(self.execution_repository.create_execution, context, pipeline.name, "running")
        overall_status = AgentStatus.SUCCESS

        for step in pipeline.steps:
            if not step.enabled:
                continue

            result = await self._execute_step(step, context)
            context.agent_results[step.name] = result
            context.execution_logs.extend(result.logs)
            await asyncio.gather(
                asyncio.to_thread(self.execution_repository.append_logs, execution_id, result.logs),
                asyncio.to_thread(self.execution_repository.append_artifacts, execution_id, step.name, result.artifacts),
            )
            context.state[step.name] = result.payload

            if result.status == AgentStatus.ERROR:
                overall_status = AgentStatus.ERROR
                if not step.continue_on_error:
                    break

        git_payload = context.state.get("git")
        git_result = None if not git_payload else git_payload.get("git_result")
        summary = ExecutionSummary(
            correlation_id=context.correlation_id,
            status=overall_status,
            pipeline=pipeline.name,
            request=context.request,
            results=context.agent_results,
            artifacts_root=request.target_root,
            logs=context.execution_logs,
            git=git_result,
        )
        await asyncio.to_thread(self.execution_repository.complete_execution, execution_id, summary)
        return summary

    async def _execute_step(self, step: PipelineStep, context: ExecutionContext) -> AgentResult:
        agent = self.agents.get(step.agent)
        if agent is None:
            return AgentResult(
                agent_name=step.agent,
                status=AgentStatus.ERROR,
                errors=[f"Agent '{step.agent}' is not registered."],
            )

        attempts = max(step.retries + 1, 1)
        last_result: AgentResult | None = None

        for attempt in range(1, attempts + 1):
            try:
                execution = agent.execute(context)
                result = await asyncio.wait_for(execution, timeout=step.timeout_seconds) if step.timeout_seconds else await execution
            except asyncio.TimeoutError:
                result = AgentResult(
                    agent_name=step.agent,
                    status=AgentStatus.ERROR,
                    errors=[f"Step '{step.name}' timed out after {step.timeout_seconds} seconds."],
                )
            except Exception as exc:
                result = AgentResult(
                    agent_name=step.agent,
                    status=AgentStatus.ERROR,
                    errors=[str(exc)],
                )

            if result.status != AgentStatus.ERROR or attempt == attempts:
                return result

            last_result = result
            await asyncio.sleep(step.retry_backoff_seconds * attempt)

        return last_result or AgentResult(agent_name=step.agent, status=AgentStatus.ERROR, errors=["Unknown execution failure."])
