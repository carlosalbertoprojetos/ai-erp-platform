from __future__ import annotations

from pathlib import Path

from domain.models import SecurityFinding, SecurityReport


class SecurityScanner:
    def scan(self, project_root: Path) -> SecurityReport:
        checks = [
            "No use of eval/exec in generated Python modules.",
            "Bearer authentication dependency is wired into the API routes.",
            "Secrets are loaded from environment variables.",
        ]
        findings: list[SecurityFinding] = []
        api_file = project_root / "app" / "presentation" / "api.py"
        auth_file = project_root / "app" / "security" / "auth.py"

        for file_path in project_root.rglob("*.py"):
            source = file_path.read_text(encoding="utf-8")
            if "eval(" in source or "exec(" in source:
                findings.append(
                    SecurityFinding(
                        severity="high",
                        title="Dynamic code execution detected",
                        details="Generated code must not execute arbitrary code paths.",
                        file_path=str(file_path),
                        recommendation="Remove eval/exec usage and use explicit control flow.",
                    )
                )

        if api_file.exists():
            api_source = api_file.read_text(encoding="utf-8")
            if "Depends(get_bearer_token)" not in api_source:
                findings.append(
                    SecurityFinding(
                        severity="high",
                        title="API routes missing authentication dependency",
                        details="Generated routes must require bearer authentication.",
                        file_path=str(api_file),
                        recommendation="Add Depends(get_bearer_token) to protected endpoints.",
                    )
                )
        else:
            findings.append(
                SecurityFinding(
                    severity="high",
                    title="API module missing",
                    details="The presentation layer was not generated.",
                    file_path=str(api_file),
                    recommendation="Regenerate the backend service before continuing.",
                )
            )

        if auth_file.exists():
            auth_source = auth_file.read_text(encoding="utf-8")
            if "os.getenv" not in auth_source:
                findings.append(
                    SecurityFinding(
                        severity="medium",
                        title="Authentication secret not externalized",
                        details="Auth configuration should be sourced from environment variables.",
                        file_path=str(auth_file),
                        recommendation="Load API tokens from environment variables instead of literals.",
                    )
                )

        status = "passed" if not any(item.severity == "high" for item in findings) else "failed"
        return SecurityReport(status=status, findings=findings, checks=checks)
