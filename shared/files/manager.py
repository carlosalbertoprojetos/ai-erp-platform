from __future__ import annotations

from pathlib import Path

from domain.exceptions import FileSafetyError
from domain.models import FileArtifact, FileOperation, FileWriteResult


class SafeFileManager:
    def apply(self, root_path: str, artifacts: list[FileArtifact], dry_run: bool = False) -> FileWriteResult:
        root = Path(root_path).resolve()
        written_files: list[str] = []
        deleted_files: list[str] = []
        created_files: list[str] = []
        updated_files: list[str] = []
        unchanged_files: list[str] = []

        for artifact in artifacts:
            destination = (root / artifact.path).resolve()
            if root not in destination.parents and destination != root:
                raise FileSafetyError(f"Refusing to write outside managed root: {destination}")

            if artifact.operation == FileOperation.DELETE:
                deleted_files.append(str(destination))
                if not dry_run and destination.exists():
                    destination.unlink()
                continue

            existing_content = destination.read_text(encoding="utf-8") if destination.exists() else None
            if existing_content == artifact.content:
                unchanged_files.append(str(destination))
                continue

            written_files.append(str(destination))
            if destination.exists():
                updated_files.append(str(destination))
            else:
                created_files.append(str(destination))

            if dry_run:
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(artifact.content, encoding="utf-8")

        return FileWriteResult(
            root_path=str(root),
            dry_run=dry_run,
            written_files=written_files,
            deleted_files=deleted_files,
            created_files=created_files,
            updated_files=updated_files,
            unchanged_files=unchanged_files,
        )
