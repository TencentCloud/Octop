"""Refuse mutating a storage backend linked as the backup remote."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from octop.config import BackupConfig, load_config
from octop.infra.backup.auto import persist_backup_config
from octop.infra.backup.remote.guards import raise_if_backup_remote_backend
from octop.infra.errors import ErrorCode, OctopError


def test_raise_if_backup_remote_backend_delete(tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    load_config(cfg)
    persist_backup_config(cfg, BackupConfig(remote_backend_id=7, remote_enabled=False))
    with pytest.raises(OctopError) as exc_info:
        raise_if_backup_remote_backend(config_path=cfg, backend_id=7, action="delete")
    assert exc_info.value.code == ErrorCode.STORAGE_BACKEND_BACKUP_REMOTE
    assert exc_info.value.details["reason"] == "backup_remote"
    assert exc_info.value.details["action"] == "deleted"


def test_raise_if_backup_remote_backend_allows_other_id(tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    load_config(cfg)
    persist_backup_config(cfg, BackupConfig(remote_backend_id=7))
    raise_if_backup_remote_backend(config_path=cfg, backend_id=8, action="delete")


@pytest.mark.asyncio
async def test_delete_storage_backend_refuses_backup_remote(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from octop.api.routers import storage_backends as sb

    cfg = tmp_path / "config.json"
    load_config(cfg)
    persist_backup_config(cfg, BackupConfig(remote_backend_id=3))

    row = MagicMock(id=3, name="octop-backup-remote")
    server = MagicMock()
    server.paths.config = cfg
    server.services.storage_backend_repo.get.return_value = row
    server.app_runtime = MagicMock()

    with pytest.raises(OctopError) as exc_info:
        await sb.delete_storage_backend(backend_id=3, server=server)
    assert exc_info.value.code == ErrorCode.STORAGE_BACKEND_BACKUP_REMOTE
    server.services.storage_backend_repo.delete.assert_not_called()


@pytest.mark.asyncio
async def test_patch_storage_backend_refuses_rename_and_disable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from octop.api.routers import storage_backends as sb

    cfg = tmp_path / "config.json"
    load_config(cfg)
    persist_backup_config(cfg, BackupConfig(remote_backend_id=3, remote_enabled=True))

    row = MagicMock(
        id=3,
        name="octop-backup-remote",
        kind="webdav",
        endpoint="https://dav.example/",
        access_key="u",
        secret_key="p",
        bucket=None,
        region=None,
        config_json="{}",
        note=None,
        enabled=1,
        created_at=0,
        updated_at=0,
    )
    server = MagicMock()
    server.paths.config = cfg
    server.services.storage_backend_repo.get.return_value = row
    server.services.storage_backend_repo.get_by_name.return_value = None
    server.app_runtime = MagicMock()

    with pytest.raises(OctopError) as exc_info:
        await sb.patch_storage_backend(
            backend_id=3,
            body=sb.StorageBackendPatchBody(name="renamed"),
            server=server,
        )
    assert exc_info.value.code == ErrorCode.STORAGE_BACKEND_BACKUP_REMOTE
    assert exc_info.value.details["action"] == "renamed"

    with pytest.raises(OctopError) as exc_info:
        await sb.patch_storage_backend(
            backend_id=3,
            body=sb.StorageBackendPatchBody(enabled=False),
            server=server,
        )
    assert exc_info.value.code == ErrorCode.STORAGE_BACKEND_BACKUP_REMOTE
    assert exc_info.value.details["action"] == "disabled"

    with pytest.raises(OctopError) as exc_info:
        await sb.patch_storage_backend(
            backend_id=3,
            body=sb.StorageBackendPatchBody(kind="s3"),
            server=server,
        )
    assert exc_info.value.code == ErrorCode.STORAGE_BACKEND_BACKUP_REMOTE
    assert exc_info.value.details["action"] == "changed"
