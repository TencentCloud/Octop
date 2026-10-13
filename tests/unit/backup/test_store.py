"""Unit tests for on-disk backup store."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from octop.infra.backup.store import (
    BackupContentFlags,
    delete_backup_file,
    is_auto_backup_filename,
    list_backup_files,
    normalize_backup_filename,
    peek_backup_contents,
    prune_auto_backups,
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


def test_created_at_from_auto_filename(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / ".octop")
    name = "octop-auto-backup-20260721T020000Z.tar.gz"
    write_backup_file(layout, name, b"x")
    items = list_backup_files(layout)
    assert len(items) == 1
    assert items[0].created_at == "2026-07-21T02:00:00+00:00"
    assert is_auto_backup_filename(name)
    assert not is_auto_backup_filename("octop-backup-20260721T020000Z.tar.gz")


def test_prune_auto_backups_keeps_newest_and_spares_manual(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / ".octop")
    write_backup_file(layout, "octop-backup-20260101T000000Z.tar.gz", b"manual")
    write_backup_file(layout, "octop-auto-backup-20260101T010000Z.tar.gz", b"a1")
    write_backup_file(layout, "octop-auto-backup-20260102T010000Z.tar.gz", b"a2")
    write_backup_file(layout, "octop-auto-backup-20260103T010000Z.tar.gz", b"a3")

    deleted = prune_auto_backups(layout, keep=2)
    assert set(deleted) == {"octop-auto-backup-20260101T010000Z.tar.gz"}
    names = {f.name for f in list_backup_files(layout)}
    assert names == {
        "octop-backup-20260101T000000Z.tar.gz",
        "octop-auto-backup-20260102T010000Z.tar.gz",
        "octop-auto-backup-20260103T010000Z.tar.gz",
    }


def test_prune_auto_backups_keep_zero_deletes_all_auto(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / ".octop")
    write_backup_file(layout, "octop-backup-20260101T000000Z.tar.gz", b"manual")
    write_backup_file(layout, "octop-auto-backup-20260101T010000Z.tar.gz", b"a1")
    deleted = prune_auto_backups(layout, keep=0)
    assert deleted == ["octop-auto-backup-20260101T010000Z.tar.gz"]
    names = {f.name for f in list_backup_files(layout)}
    assert names == {"octop-backup-20260101T000000Z.tar.gz"}


def test_peek_backup_contents_reads_manifest(tmp_path: Path) -> None:
    from octop.config import DatabaseConfig
    from octop.infra.backup.system_archive import create_system_backup
    from octop.infra.db.migrate import run_migrations
    from octop.infra.db.pool import SqlitePool

    layout = PathLayout(tmp_path / ".octop")
    layout.root.mkdir()
    pool = SqlitePool(layout.db)
    run_migrations(pool)
    archive = tmp_path / "peek.tar.gz"
    create_system_backup(
        paths=layout,
        agent_rows=[],
        pool=pool,
        db_config=DatabaseConfig(),
        dest=archive,
        include_config=False,
        include_workspaces=False,
        include_skill_packages=False,
        include_plugins=False,
        include_knowledge=False,
        include_chats=False,
    )
    pool.close()
    assert peek_backup_contents(archive) == BackupContentFlags(
        includes_config=False,
        includes_workspaces=False,
        includes_skill_packages=False,
        includes_plugins=False,
        includes_knowledge=False,
        includes_chats=False,
    )
    write_backup_file(layout, "octop-backup-peek.tar.gz", archive.read_bytes())
    item = list_backup_files(layout)[0]
    assert item.includes_config is False
    assert item.includes_workspaces is False
    assert item.includes_skill_packages is False
    assert item.includes_plugins is False
    assert item.includes_knowledge is False
    assert item.includes_chats is False


def _write_tar_gz_with_members(path: Path, members: list[tuple[str, bytes]]) -> None:
    import io
    import tarfile

    with tarfile.open(path, mode="w:gz") as tf:
        for name, payload in members:
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))


def _minimal_manifest_json(**flags: bool) -> bytes:
    import json

    payload = {
        "manifest_version": 1,
        "octop_version": "0.0.0-test",
        "schema_version": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
        "home": "/tmp",
        "db_file": "db/octop.db",
        "agents": [],
        "includes_config": flags.get("includes_config", True),
        "includes_env": False,
        "includes_skill_packages": flags.get("includes_skill_packages", True),
        "includes_plugins": flags.get("includes_plugins", False),
        "includes_knowledge": flags.get("includes_knowledge", False),
        "includes_chats": flags.get("includes_chats", True),
    }
    return json.dumps(payload).encode("utf-8")


def test_peek_reads_first_member_manifest_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Peek must not scan past the first member (full-scan would read the blob)."""
    import builtins
    import os
    import time

    archive = tmp_path / "first-member.tar.gz"
    # Incompressible so the gzip stays large; a full member scan would read most of it.
    blob = os.urandom(4 * 1024 * 1024)
    _write_tar_gz_with_members(
        archive,
        [
            (
                "manifest.json",
                _minimal_manifest_json(
                    includes_config=False,
                    includes_skill_packages=False,
                    includes_plugins=False,
                    includes_knowledge=False,
                    includes_chats=False,
                ),
            ),
            ("payload.bin", blob),
        ],
    )
    archive_size = archive.stat().st_size
    assert archive_size > 2 * 1024 * 1024

    bytes_read = 0
    real_open = builtins.open

    def counting_open(file, mode="r", *args, **kwargs):  # noqa: ANN001
        nonlocal bytes_read
        handle = real_open(file, mode, *args, **kwargs)
        if "b" not in mode:
            return handle
        try:
            if Path(file).resolve() != archive.resolve():
                return handle
        except (TypeError, OSError, ValueError):
            return handle

        class _CountingReader:
            def __init__(self, raw: object) -> None:
                self._raw = raw

            def read(self, size: int = -1) -> bytes:
                nonlocal bytes_read
                data = self._raw.read(size)  # type: ignore[attr-defined]
                bytes_read += len(data)
                return bytes(data)

            def __getattr__(self, name: str) -> object:
                return getattr(self._raw, name)

            def __enter__(self) -> _CountingReader:
                return self

            def __exit__(self, *exc: object) -> None:
                close = getattr(self._raw, "close", None)
                if callable(close):
                    close()

        return _CountingReader(handle)

    monkeypatch.setattr(builtins, "open", counting_open)
    started = time.perf_counter()
    flags = peek_backup_contents(archive)
    elapsed = time.perf_counter() - started

    assert flags == BackupContentFlags(
        includes_config=False,
        includes_workspaces=False,
        includes_skill_packages=False,
        includes_plugins=False,
        includes_knowledge=False,
        includes_chats=False,
    )
    # First-member peek should read far less than the on-disk archive size.
    assert bytes_read < archive_size // 4
    assert elapsed < 2.0


def test_peek_skips_scan_when_manifest_not_first(tmp_path: Path) -> None:
    archive = tmp_path / "manifest-second.tar.gz"
    _write_tar_gz_with_members(
        archive,
        [
            ("readme.txt", b"not a manifest"),
            (
                "manifest.json",
                _minimal_manifest_json(includes_config=False, includes_chats=False),
            ),
        ],
    )
    # Deliberately no deep scan: treat as full contents.
    assert peek_backup_contents(archive) == BackupContentFlags()
