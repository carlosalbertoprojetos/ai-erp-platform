from __future__ import annotations

from pathlib import Path

from domain.models import GitConfig
from infrastructure.git.github import GitHubService
from shared.observability.logger import JsonExecutionLogger


def test_git_service_returns_disabled_when_not_enabled(tmp_path: Path):
    service = GitHubService()
    result = service.apply(tmp_path, GitConfig(enabled=False), correlation_id="12345678")

    assert result["performed"] is False
    assert result["reason"] == "Git automation disabled."


def test_git_service_returns_error_for_non_repo(tmp_path: Path):
    service = GitHubService()
    result = service.apply(tmp_path, GitConfig(enabled=True, auto_commit=True), correlation_id="12345678")

    assert result["performed"] is False
    assert result["reason"] == "Target project is not a git repository."


def test_json_logger_writes_per_agent_log(tmp_path: Path):
    logger = JsonExecutionLogger(root_path=str(tmp_path))
    entry = logger.log("corr-1", "architect", "info", "hello", {"feature": "finance"})

    log_file = tmp_path / "corr-1" / "architect.jsonl"
    assert entry.agent_name == "architect"
    assert log_file.exists()
    assert "finance" in log_file.read_text(encoding="utf-8")
