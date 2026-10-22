"""CLI backup output placement and failure cleanup."""

from __future__ import annotations

import errno
import os
import tarfile
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from octop.cli.commands import backup as backup_cmd
from octop.cli.main import cli


def _assert_archive(path: Path) -> None:
    with tarfile.open(path, "r:gz") as archive:
        assert "manifest.json" in archive.getnames()
        database = archive.extractfile("db/octop.db")
        assert database is not None
        assert database.read(16) == b"SQLite format 3\x00"


@pytest.mark.parametrize("relative", [False, True], ids=["absolute", "relative"])
def test_create_backup_output_on_another_filesystem(
    tmp_octop_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: bool
) -> None:
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "mounted-volume" / "nested" / "backup.tar.gz"
    argument = output.relative_to(tmp_path) if relative else output
    replace = os.replace

    def same_filesystem_replace(src: Any, dst: Any) -> None:
        # Model a separate mount at output.parent, including its staging directory.
        if Path(dst).resolve() == output and not Path(src).resolve().is_relative_to(output.parent):
            raise OSError(errno.EXDEV, "Cross-device link", str(src), str(dst))
        replace(src, dst)

    monkeypatch.setattr(os, "replace", same_filesystem_replace)
    result = CliRunner().invoke(
        cli, ["backup", "create", "--home", str(tmp_octop_home), "--output", str(argument)]
    )

    assert result.exit_code == 0, repr(result.exception)
    assert "wrote " in result.output
    _assert_archive(output)
    assert list(output.parent.iterdir()) == [output]


def test_create_backup_replaces_existing_output(tmp_octop_home: Path, tmp_path: Path) -> None:
    output = tmp_path / "backup.tar.gz"
    output.write_bytes(b"old backup")

    result = CliRunner().invoke(
        cli, ["backup", "create", "--home", str(tmp_octop_home), "-o", str(output)]
    )

    assert result.exit_code == 0, repr(result.exception)
    _assert_archive(output)
    assert list(tmp_path.iterdir()) == [output]


def test_create_backup_failure_preserves_existing_output(
    tmp_octop_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "backup.tar.gz"
    output.write_bytes(b"old backup")
    staged: list[Path] = []

    def fail_backup(*, dest: Path, **_kwargs: Any) -> str:
        staged.append(dest)
        dest.write_bytes(b"incomplete backup")
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(backup_cmd, "create_system_backup", fail_backup)
    result = CliRunner().invoke(
        cli, ["backup", "create", "--home", str(tmp_octop_home), "-o", str(output)]
    )

    assert result.exit_code != 0
    assert isinstance(result.exception, OSError)
    assert result.exception.errno == errno.ENOSPC
    assert "wrote " not in result.output
    assert output.read_bytes() == b"old backup"
    assert len(staged) == 1
    assert not staged[0].parent.exists()
    assert list(tmp_path.iterdir()) == [output]


def test_create_backup_without_output_uses_backup_store(tmp_octop_home: Path) -> None:
    result = CliRunner().invoke(cli, ["backup", "create", "--home", str(tmp_octop_home)])

    assert result.exit_code == 0, repr(result.exception)
    archives = list((tmp_octop_home / "backups").glob("octop-backup-*.tar.gz"))
    assert len(archives) == 1
    _assert_archive(archives[0])


def test_cross_filesystem_copy_failure_preserves_existing_output(
    tmp_octop_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "backup.tar.gz"
    output.write_bytes(b"old backup")
    replace = os.replace
    staged: list[Path] = []

    def cross_device_replace(src: Any, dst: Any) -> None:
        if Path(dst) == output:
            raise OSError(errno.EXDEV, "Cross-device link")
        replace(src, dst)

    def fail_copy(src: Any, dst: Any) -> None:
        _assert_archive(Path(src))
        path = Path(dst)
        staged.append(path)
        path.write_bytes(b"incomplete copy")
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "replace", cross_device_replace)
    monkeypatch.setattr(backup_cmd.shutil, "copy2", fail_copy)
    result = CliRunner().invoke(
        cli,
        ["backup", "create", "--home", str(tmp_octop_home), "--no-config", "-o", str(output)],
    )

    assert result.exit_code != 0
    assert isinstance(result.exception, OSError)
    assert result.exception.errno == errno.ENOSPC
    assert "wrote " not in result.output
    assert output.read_bytes() == b"old backup"
    assert len(staged) == 1
    assert not staged[0].parent.exists()
    assert list(tmp_path.iterdir()) == [output]


def test_output_permission_error_is_not_treated_as_cross_filesystem(
    tmp_octop_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "backup.tar.gz"
    output.write_bytes(b"old backup")
    replace = os.replace

    def denied_replace(src: Any, dst: Any) -> None:
        if Path(dst) == output:
            raise PermissionError(errno.EACCES, "Permission denied")
        replace(src, dst)

    def unexpected_copy(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("permission failures must not fall back to copying")

    monkeypatch.setattr(os, "replace", denied_replace)
    monkeypatch.setattr(backup_cmd.shutil, "copy2", unexpected_copy)
    result = CliRunner().invoke(
        cli,
        ["backup", "create", "--home", str(tmp_octop_home), "--no-config", "-o", str(output)],
    )

    assert result.exit_code != 0
    assert isinstance(result.exception, PermissionError)
    assert output.read_bytes() == b"old backup"
    assert list(tmp_path.iterdir()) == [output]
