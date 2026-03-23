from __future__ import annotations

from pathlib import Path

import pytest

from domain.exceptions import FileSafetyError
from domain.models import FileArtifact, FileOperation
from shared.files.manager import SafeFileManager


def test_file_manager_writes_updates_and_tracks_unchanged_files(tmp_path: Path):
    manager = SafeFileManager()
    first = manager.apply(
        str(tmp_path),
        [FileArtifact(path="nested/example.txt", content="hello")],
        dry_run=False,
    )
    second = manager.apply(
        str(tmp_path),
        [FileArtifact(path="nested/example.txt", content="hello")],
        dry_run=False,
    )
    third = manager.apply(
        str(tmp_path),
        [FileArtifact(path="nested/example.txt", content="updated")],
        dry_run=False,
    )
    fourth = manager.apply(
        str(tmp_path),
        [FileArtifact(path="nested/example.txt", operation=FileOperation.DELETE)],
        dry_run=False,
    )

    assert first.created_files
    assert second.unchanged_files
    assert third.updated_files
    assert fourth.deleted_files
    assert not (tmp_path / "nested" / "example.txt").exists()


def test_file_manager_blocks_path_escape(tmp_path: Path):
    manager = SafeFileManager()
    with pytest.raises(FileSafetyError):
        manager.apply(
            str(tmp_path),
            [FileArtifact(path="../outside.txt", content="nope")],
            dry_run=False,
        )
