from __future__ import annotations

import json
import os
from pathlib import Path

from agents.architect.agent import ArchitectAgent
from agents.backend.agent import BackendAgent
from agents.git.agent import GitAgent
from agents.qa.agent import QAAgent
from agents.refactor.agent import RefactorAgent
from agents.security.agent import SecurityAgent
from application.agent_registry import AgentRegistry
from application.orchestrator import AgentOrchestrator
from application.settings import CoreFlowSettings
from domain.code_generation_engine import FastAPICodeGenerationEngine
from domain.models import PipelineDefinition
from domain.services import ArchitectureDomainService
from infrastructure.analysis.refactor import RefactorAnalyzer
from infrastructure.database.repository import ExecutionRepository
from infrastructure.git.github import GitHubService
from infrastructure.security.scanner import SecurityScanner
from shared.files.manager import SafeFileManager
from shared.llm.openai_provider import OpenAIProvider
from shared.llm.service import StructuredLLMService
from shared.llm.template_provider import TemplateLLMProvider
from shared.observability.logger import JsonExecutionLogger


class PipelineLoader:
    def __init__(self, config_root: str):
        self.config_root = Path(config_root)

    def load(self, name: str) -> PipelineDefinition:
        with (self.config_root / f"{name}.json").open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        return PipelineDefinition.model_validate(payload)


def _build_provider(provider_name: str):
    if provider_name == "openai":
        return OpenAIProvider()
    return TemplateLLMProvider()


def get_agents(provider_name: str = "template") -> dict:
    logger = JsonExecutionLogger()
    architecture_service = ArchitectureDomainService()
    llm_service = StructuredLLMService(_build_provider(provider_name))
    file_manager = SafeFileManager()
    code_generation_engine = FastAPICodeGenerationEngine()
    security_scanner = SecurityScanner()
    refactor_analyzer = RefactorAnalyzer()
    git_service = GitHubService()
    registry = AgentRegistry()

    for agent in [
        ArchitectAgent(logger, llm_service, architecture_service),
        BackendAgent(logger, code_generation_engine, file_manager),
        SecurityAgent(logger, security_scanner),
        QAAgent(logger, file_manager),
        RefactorAgent(logger, refactor_analyzer),
        GitAgent(logger, git_service),
    ]:
        registry.register(agent)

    return registry.all()


def build_orchestrator(provider_name: str | None = None, settings: CoreFlowSettings | None = None) -> AgentOrchestrator:
    resolved_settings = settings or CoreFlowSettings.from_env()
    resolved_provider = provider_name or os.getenv("COREFLOW_LLM_PROVIDER", resolved_settings.default_provider)
    agents = get_agents(provider_name=resolved_provider)
    pipeline_loader = PipelineLoader(config_root=str(Path(__file__).parent / "pipelines"))
    repository = ExecutionRepository(resolved_settings.database_url)
    return AgentOrchestrator(agents=agents, pipeline_loader=pipeline_loader, execution_repository=repository)
