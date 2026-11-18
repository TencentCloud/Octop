"""Unit tests for remote backup backend → engine resolution."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from octop.config import BackupConfig
from octop.infra.backup.remote.resolve import (
    provider_from_backend,
    provider_kwargs_from_backend,
    raise_remote_mirror_failed,
    remote_summary,
    resolve_remote_engine,
)
from octop.infra.db.repos.backends import BackendRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout


def _row(**overrides: Any) -> BackendRow:
    base = BackendRow(
        id=1,
        name="octop-backup-remote",
        kind="webdav",
        endpoint="https://dav.example/remote.php/dav/files/u/",
        access_key="alice",
        secret_key="secret",
        bucket=None,
        region=None,
        config_json='{"base_dir":"octop-backups","verify_ssl":true,"allow_insecure":false}',
        note=None,
        enabled=1,
        created_at=0,
        updated_at=0,
    )
    return replace(base, **overrides) if overrides else base


def test_provider_kwargs_from_webdav_row() -> None:
    kwargs = provider_kwargs_from_backend(_row())
    assert kwargs["url"].startswith("https://dav.example/")
    assert kwargs["username"] == "alice"
    assert kwargs["password"] == "secret"
    assert kwargs["base_dir"] == "octop-backups"
    assert kwargs["verify_ssl"] is True


def test_provider_kwargs_from_cos_row_uses_base_dir() -> None:
    kwargs = provider_kwargs_from_backend(
        _row(
            kind="cos",
            endpoint="cos.ap-shanghai.myqcloud.com",
            access_key="AKIDxxx",
            secret_key="secret",
            bucket="voyah-sd-pic-1301141550",
            region="ap-shanghai",
            config_json='{"base_dir":"/Apps"}',
        )
    )
    assert kwargs["bucket"] == "voyah-sd-pic-1301141550"
    assert kwargs["base_dir"] == "Apps"
    assert kwargs["region"] == "ap-shanghai"


def test_provider_kwargs_from_cos_accepts_prefix_alias() -> None:
    kwargs = provider_kwargs_from_backend(
        _row(
            kind="cos",
            bucket="b",
            region="ap-guangzhou",
            config_json='{"prefix":"legacy"}',
        )
    )
    assert kwargs["base_dir"] == "legacy"


def test_provider_from_backend_rejects_unimplemented_kind() -> None:
    with pytest.raises(OctopError) as exc_info:
        provider_from_backend(_row(kind="dropbox"))
    assert exc_info.value.code == ErrorCode.BACKUP_REMOTE_UNSUPPORTED


def test_provider_from_backend_rejects_disabled() -> None:
    with pytest.raises(OctopError) as exc_info:
        provider_from_backend(_row(enabled=0))
    assert exc_info.value.code == ErrorCode.BACKUP_REMOTE_FAILED


def test_resolve_remote_engine_none_when_disabled(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / "home")
    engine = resolve_remote_engine(
        paths=layout,
        backup=BackupConfig(remote_enabled=False, remote_backend_id=1),
        get_backend=lambda _id: _row(),
    )
    assert engine is None


def test_resolve_remote_engine_fail_closed_missing_backend(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / "home")
    with pytest.raises(OctopError) as exc_info:
        resolve_remote_engine(
            paths=layout,
            backup=BackupConfig(remote_enabled=True, remote_backend_id=99),
            get_backend=lambda _id: None,
        )
    assert exc_info.value.code == ErrorCode.BACKUP_REMOTE_FAILED


def test_resolve_remote_engine_builds_webdav(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / "home")
    engine = resolve_remote_engine(
        paths=layout,
        backup=BackupConfig(remote_enabled=True, remote_backend_id=1),
        get_backend=lambda _id: _row(),
    )
    assert engine is not None


def test_remote_summary_includes_last_mirror(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / "home")
    layout.backups_dir.mkdir(parents=True)
    from octop.infra.backup.remote.index import MirrorIndex, MirrorIndexEntry

    index = MirrorIndex.for_paths(layout)
    index.set(
        "octop-auto-backup-20260101T000000Z.tar.gz",
        MirrorIndexEntry(status="remote_ok", checked_at="2026-01-01T00:00:00+00:00"),
    )
    summary = remote_summary(
        paths=layout,
        backup=BackupConfig(remote_enabled=True, remote_backend_id=1),
        get_backend=lambda _id: _row(),
    )
    assert summary["kind"] == "webdav"
    assert summary["last_mirror"]["status"] == "remote_ok"
    assert "secret" not in str(summary)


def test_raise_remote_mirror_failed_sets_detail() -> None:
    with pytest.raises(OctopError) as exc_info:
        raise_remote_mirror_failed("size mismatch")
    assert exc_info.value.code == ErrorCode.BACKUP_REMOTE_FAILED
    assert exc_info.value.details["detail"] == "size mismatch"
