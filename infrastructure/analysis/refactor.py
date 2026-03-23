from __future__ import annotations

import difflib
from collections import Counter
from pathlib import Path

from domain.models import RefactorReport, RefactorSuggestion


class RefactorAnalyzer:
    def analyze(self, project_root: Path) -> RefactorReport:
        python_files = sorted(project_root.rglob("*.py"))
        repeated_lines: Counter[str] = Counter()
        per_file_contents: dict[Path, list[str]] = {}

        for file_path in python_files:
            lines = [
                line
                for line in file_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            per_file_contents[file_path] = lines
            repeated_lines.update(lines)

        duplicate_count = sum(count - 1 for count in repeated_lines.values() if count > 1)
        total_lines = max(sum(len(lines) for lines in per_file_contents.values()), 1)
        duplication_ratio = duplicate_count / total_lines
        suggestions: list[RefactorSuggestion] = []
        frequent_lines = [line for line, count in repeated_lines.items() if count > 2 and "import " not in line][:3]

        if frequent_lines and python_files:
            target_file = python_files[0]
            original = target_file.read_text(encoding="utf-8").splitlines()
            improved = original[:]
            improved.insert(0, "# Repeated logic detected: consider extracting a shared helper.")
            diff = "\n".join(
                difflib.unified_diff(
                    original,
                    improved,
                    fromfile=str(target_file),
                    tofile=str(target_file),
                    lineterm="",
                )
            )
            suggestions.append(
                RefactorSuggestion(
                    title="Repeated statements detected",
                    details=f"Repeated lines such as '{frequent_lines[0]}' suggest extractable shared behavior.",
                    diff=diff,
                )
            )

        return RefactorReport(duplication_ratio=duplication_ratio, suggestions=suggestions)
