"""Refuse mutating a storage backend linked as the backup remote."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from octop.config import BackupConfig, load_config
from octop.infra.backup.auto import persist_backup_config
from octop.infra.backup.remote.guards import (
    raise_if_backup_remote_backend,
    unlink_backup_remote_backend,
)
from octop.infra.errors import ErrorCode, OctopError


def test_raise_if_delete_blocked_when_occupied(tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    load_config(cfg)
    persist_backup_config(cfg, BackupConfig(remote_backend_id=7, remote_enabled=True))
    with pytest.raises(OctopError) as exc_info:
        raise_if_backup_remote_backend(config_path=cfg, backend_id=7, action="delete")
    assert exc_info.value.code == ErrorCode.STORAGE_BACKEND_BACKUP_REMOTE
    assert exc_info.value.details["action"] == "deleted"


def test_raise_if_delete_allowed_when_not_occupied(tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    load_config(cfg)
    persist_backup_config(cfg, BackupConfig(remote_backend_id=7, remote_enabled=False))
    raise_if_backup_remote_backend(config_path=cfg, backend_id=7, action="delete")


def test_raise_if_backup_remote_backend_allows_other_id(tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    load_config(cfg)
    persist_backup_config(cfg, BackupConfig(remote_backend_id=7, remote_enabled=True))
    raise_if_backup_remote_backend(config_path=cfg, backend_id=8, action="delete")


@pytest.mark.asyncio
async def test_delete_storage_backend_refuses_when_occupied(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from octop.api.routers import storage_backends as sb

    cfg = tmp_path / "config.json"
    load_config(cfg)
    persist_backup_config(cfg, BackupConfig(remote_backend_id=3, remote_enabled=True))

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
async def test_delete_storage_backend_unlinks_dangling_then_deletes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from octop.api.routers import storage_backends as sb

    cfg = tmp_path / "config.json"
    load_config(cfg)
    persist_backup_config(cfg, BackupConfig(remote_backend_id=3, remote_enabled=False))

    def _upd(server: MagicMock, backup: BackupConfig) -> object:
        persist_backup_config(server.paths.config, backup)
        return load_config(server.paths.config)

    monkeypatch.setattr(
        "octop.infra.backup.remote.guards.update_server_backup_config",
        _upd,
    )

    row = MagicMock(id=3, name="octop-backup-remote")
    server = MagicMock()
    server.paths.config = cfg
    server.services.storage_backend_repo.get.return_value = row
    server.app_runtime = MagicMock()
    server.app_runtime.agent_registry.find_agents_using_storage_backend.return_value = []

    await sb.delete_storage_backend(backend_id=3, server=server)
    server.services.storage_backend_repo.delete.assert_called_once_with(3)
    saved = load_config(cfg).backup
    assert saved.remote_backend_id is None
    assert saved.remote_enabled is False


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


def test_unlink_backup_remote_backend_noop_when_occupied(tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    load_config(cfg)
    persist_backup_config(cfg, BackupConfig(remote_backend_id=7, remote_enabled=True))
    server = MagicMock()
    server.paths.config = cfg
    assert unlink_backup_remote_backend(server=server, backend_id=7) is False
    assert load_config(cfg).backup.remote_backend_id == 7
