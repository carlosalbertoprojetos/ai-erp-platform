from __future__ import annotations

from pathlib import Path

from domain.code_generation_engine import FastAPICodeGenerationEngine
from domain.models import FeatureRequest
from domain.services import ArchitectureDomainService, pascalize, slugify
from infrastructure.analysis.refactor import RefactorAnalyzer
from infrastructure.security.scanner import SecurityScanner


def test_slugify_and_pascalize_helpers():
    assert slugify("Finance Ledger") == "finance_ledger"
    assert pascalize("finance_ledger") == "FinanceLedger"


def test_architecture_service_builds_plan():
    service = ArchitectureDomainService()
    plan = service.design(
        FeatureRequest(
            title="Finance Ledger",
            description="Track company expenses",
            module_name="finance",
            entities=["LedgerEntry"],
            capabilities=["create_entry", "list_entries"],
        )
    )

    assert plan.modules[0].name == "finance"
    assert len(plan.modules[0].endpoints) == 2
    assert "JSON" in plan.policies[1]


def test_code_generation_engine_creates_clean_architecture_files(tmp_path: Path):
    plan = ArchitectureDomainService().design(
        FeatureRequest(title="Catalog", description="Catalog service", module_name="catalog", entities=["Product"])
    )
    project = FastAPICodeGenerationEngine().generate(plan, str(tmp_path))

    assert project.root_path.endswith("catalog\\backend") or project.root_path.endswith("catalog/backend")
    paths = {artifact.path for artifact in project.files}
    assert "app/domain/repositories.py" in paths
    assert "app/application/use_cases.py" in paths
    generated_use_cases = next(artifact.content for artifact in project.files if artifact.path == "app/application/use_cases.py")
    assert "from app.domain.repositories import ProductRepository" in generated_use_cases


def test_security_and_refactor_services_scan_generated_project(tmp_path: Path):
    plan = ArchitectureDomainService().design(
        FeatureRequest(title="Catalog", description="Catalog service", module_name="catalog", entities=["Product"])
    )
    project = FastAPICodeGenerationEngine().generate(plan, str(tmp_path))
    project_root = Path(project.root_path)
    for artifact in project.files:
        path = project_root / artifact.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.content, encoding="utf-8")

    security_report = SecurityScanner().scan(project_root)
    refactor_report = RefactorAnalyzer().analyze(project_root)

    assert security_report.status == "passed"
    assert security_report.checks
    assert refactor_report.duplication_ratio >= 0
