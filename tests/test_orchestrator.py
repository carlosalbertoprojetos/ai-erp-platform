from __future__ import annotations

from pathlib import Path

from apps.orchestrator.orchestrator.registry import build_orchestrator
from domain.models import AgentStatus, RunRequest


async def test_pipeline_generates_backend_and_tests(tmp_path: Path):
    orchestrator = build_orchestrator()
    request = RunRequest(
        request={
            "title": "Finance Ledger",
            "description": "Create a finance ledger service for expense tracking.",
            "module_name": "finance",
            "entities": ["LedgerEntry"],
            "capabilities": ["create_entry", "list_entries"],
        },
        target_root=str(tmp_path),
    )

    result = await orchestrator.run(request)

    assert result.status == AgentStatus.SUCCESS
    project_root = Path(result.results["backend"].payload["project_root"])
    assert (project_root / "app" / "main.py").exists()
    assert (project_root / "app" / "domain" / "repositories.py").exists()
    assert (project_root / "tests" / "test_api.py").exists()
    assert result.results["backend"].payload["created_files"]
    assert result.results["qa"].payload["qa_summary"]["coverage_percent"] >= 85
