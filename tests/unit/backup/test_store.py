"""Unit tests for on-disk backup store."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from octop.infra.backup.store import (
    delete_backup_file,
    list_backup_files,
    normalize_backup_filename,
    read_backup_file,
    write_backup_file,
)
from octop.infra.errors import OctopError
from octop.infra.utils.paths import PathLayout


def test_backups_dir_paths(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / ".octop")
    assert layout.backups_dir == tmp_path / ".octop" / "backups"
    out = layout.ensure_backups_dir()
    assert out.is_dir()
    assert layout.backup_file("x.tar.gz") == layout.backups_dir / "x.tar.gz"


def test_store_roundtrip(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / ".octop")
    write_backup_file(layout, "octop-backup-test.tar.gz", b"payload")
    items = list_backup_files(layout)
    assert len(items) == 1
    assert items[0].name == "octop-backup-test.tar.gz"
    assert read_backup_file(layout, "octop-backup-test.tar.gz") == b"payload"
    delete_backup_file(layout, "octop-backup-test.tar.gz")
    assert list_backup_files(layout) == []


def test_reject_unsafe_filename() -> None:
    with pytest.raises(OctopError):
        normalize_backup_filename("../escape.tar.gz")
    with pytest.raises(OctopError):
        normalize_backup_filename("bad.zip")


def test_created_at_from_canonical_filename(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / ".octop")
    name = "octop-backup-20260721T013000Z.tar.gz"
    write_backup_file(layout, name, b"x")
    items = list_backup_files(layout)
    assert len(items) == 1
    assert items[0].created_at == "2026-07-21T01:30:00+00:00"
    assert "created_at" in items[0].to_dict()


def test_created_at_falls_back_without_timestamp_in_name(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / ".octop")
    write_backup_file(layout, "manual-upload.tar.gz", b"x")
    items = list_backup_files(layout)
    assert len(items) == 1
    # Must be a parseable ISO timestamp (birth or mtime), not empty
    datetime.fromisoformat(items[0].created_at)
    assert items[0].modified_at  # still present


def test_created_at_falls_back_on_invalid_filename_stamp(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / ".octop")
    # Matches regex but is not a real calendar datetime
    write_backup_file(layout, "octop-backup-20261399T999999Z.tar.gz", b"x")
    items = list_backup_files(layout)
    assert len(items) == 1
    datetime.fromisoformat(items[0].created_at)
