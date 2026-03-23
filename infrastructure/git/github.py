from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from domain.models import GitConfig, GitOperationResult


class GitHubService:
    def apply(self, project_root: Path, git_config: GitConfig, correlation_id: str) -> dict:
        if not git_config.enabled or not git_config.auto_commit:
            return GitOperationResult(performed=False, reason="Git automation disabled.").model_dump(mode="json")

        if not (project_root / ".git").exists():
            return GitOperationResult(performed=False, reason="Target project is not a git repository.").model_dump(mode="json")

        branch_name = f"{git_config.branch_prefix}/{correlation_id[:8]}"
        try:
            self._run(["git", "checkout", "-B", branch_name], cwd=project_root)
            self._run(["git", "add", "."], cwd=project_root)
            commit_result = self._run(["git", "commit", "-m", git_config.commit_message], cwd=project_root, allow_empty=True)
            commit_sha = self._run(["git", "rev-parse", "HEAD"], cwd=project_root).stdout.strip()
        except RuntimeError as exc:
            return GitOperationResult(performed=False, reason=str(exc)).model_dump(mode="json")

        pr_url = None
        if git_config.auto_pr and git_config.repo:
            pr_url = self.create_pr(
                repo=git_config.repo,
                branch=branch_name,
                title=git_config.pr_title,
                body=git_config.pr_body,
                base=git_config.base_branch,
            )

        return GitOperationResult(
            performed=True,
            branch=branch_name,
            commit_sha=commit_sha,
            pr_url=pr_url,
            reason=commit_result.stdout.strip() or commit_result.stderr.strip() or None,
        ).model_dump(mode="json")

    def create_pr(self, repo: str, branch: str, title: str, body: str, base: str = "main") -> str | None:
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            return None
        request = urllib.request.Request(
            url=f"https://api.github.com/repos/{repo}/pulls",
            data=json.dumps(
                {
                    "title": title,
                    "head": branch,
                    "base": base,
                    "body": body,
                }
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/vnd.github+json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError:
            return None
        return payload.get("html_url")

    def _run(
        self,
        command: list[str],
        cwd: Path,
        allow_empty: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False, timeout=30)
        if completed.returncode == 0:
            return completed
        if allow_empty and "nothing to commit" in completed.stdout.lower() + completed.stderr.lower():
            return completed
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"Git command failed: {' '.join(command)}")
