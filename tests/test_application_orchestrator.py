from __future__ import annotations

import asyncio

from application.orchestrator import AgentOrchestrator
from domain.models import AgentResult, AgentStatus, ExecutionContext, FeatureRequest, PipelineDefinition, PipelineStep, RunRequest


class _PipelineLoader:
    def __init__(self, pipeline: PipelineDefinition):
        self.pipeline = pipeline

    def load(self, name: str) -> PipelineDefinition:
        return self.pipeline


class _Repository:
    def __init__(self):
        self.completed = None
        self.logs = []
        self.artifacts = []

    def ensure_schema(self):
        return None

    def create_execution(self, context, pipeline_name, status="running"):
        return "exec-1"

    def append_logs(self, execution_id, logs):
        self.logs.extend(logs)

    def append_artifacts(self, execution_id, agent_name, artifacts):
        self.artifacts.extend(artifacts)

    def complete_execution(self, execution_id, summary):
        self.completed = summary


class _Agent:
    def __init__(self, name: str, status: AgentStatus):
        self.name = name
        self.status = status

    async def execute(self, context: ExecutionContext) -> AgentResult:
        return AgentResult(agent_name=self.name, status=self.status, payload={self.name: "ok"})


class _FlakyAgent:
    def __init__(self):
        self.name = "flaky"
        self.calls = 0

    async def execute(self, context: ExecutionContext) -> AgentResult:
        self.calls += 1
        status = AgentStatus.SUCCESS if self.calls == 2 else AgentStatus.ERROR
        return AgentResult(agent_name=self.name, status=status, payload={"attempt": self.calls}, errors=[] if status == AgentStatus.SUCCESS else ["temporary"])


class _SlowAgent:
    def __init__(self):
        self.name = "slow"

    async def execute(self, context: ExecutionContext) -> AgentResult:
        await asyncio.sleep(0.05)
        return AgentResult(agent_name=self.name, status=AgentStatus.SUCCESS, payload={})


async def test_application_orchestrator_stops_on_error():
    repository = _Repository()
    pipeline = PipelineDefinition(
        name="default",
        steps=[
            PipelineStep(name="a", agent="a"),
            PipelineStep(name="b", agent="b"),
        ],
    )
    orchestrator = AgentOrchestrator(
        agents={"a": _Agent("a", AgentStatus.ERROR), "b": _Agent("b", AgentStatus.SUCCESS)},
        pipeline_loader=_PipelineLoader(pipeline),
        execution_repository=repository,
    )

    summary = await orchestrator.run(RunRequest(request=FeatureRequest(title="A", description="B"), target_root="generated"))

    assert summary.status == AgentStatus.ERROR
    assert "a" in summary.results
    assert "b" not in summary.results
    assert repository.completed is not None


async def test_application_orchestrator_continues_when_configured():
    repository = _Repository()
    pipeline = PipelineDefinition(
        name="default",
        steps=[
            PipelineStep(name="a", agent="a", continue_on_error=True),
            PipelineStep(name="b", agent="b"),
        ],
    )
    orchestrator = AgentOrchestrator(
        agents={"a": _Agent("a", AgentStatus.ERROR), "b": _Agent("b", AgentStatus.SUCCESS)},
        pipeline_loader=_PipelineLoader(pipeline),
        execution_repository=repository,
    )

    summary = await orchestrator.run(RunRequest(request=FeatureRequest(title="A", description="B"), target_root="generated"))

    assert summary.status == AgentStatus.ERROR
    assert "b" in summary.results


async def test_application_orchestrator_retries_flaky_step():
    repository = _Repository()
    flaky = _FlakyAgent()
    pipeline = PipelineDefinition(name="default", steps=[PipelineStep(name="flaky", agent="flaky", retries=1)])
    orchestrator = AgentOrchestrator(
        agents={"flaky": flaky},
        pipeline_loader=_PipelineLoader(pipeline),
        execution_repository=repository,
    )

    summary = await orchestrator.run(RunRequest(request=FeatureRequest(title="A", description="B"), target_root="generated"))

    assert summary.status == AgentStatus.SUCCESS
    assert flaky.calls == 2


async def test_application_orchestrator_times_out_step():
    repository = _Repository()
    pipeline = PipelineDefinition(name="default", steps=[PipelineStep(name="slow", agent="slow", timeout_seconds=0.01)])
    orchestrator = AgentOrchestrator(
        agents={"slow": _SlowAgent()},
        pipeline_loader=_PipelineLoader(pipeline),
        execution_repository=repository,
    )

    summary = await orchestrator.run(RunRequest(request=FeatureRequest(title="A", description="B"), target_root="generated"))

    assert summary.status == AgentStatus.ERROR
    assert "timed out" in summary.results["slow"].errors[0]
