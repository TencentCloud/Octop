"""Auto/create remote mirror wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.config import BackupConfig
from octop.infra.backup import auto as auto_mod
from octop.infra.backup.remote.types import MirrorResult
from octop.infra.backup.store import BackupFileInfo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout


def _entry(name: str = "octop-auto-backup-20260101T000000Z.tar.gz") -> BackupFileInfo:
    return BackupFileInfo(
        name=name,
        size=12,
        modified_at="2026-01-01T00:00:00+00:00",
        created_at="2026-01-01T00:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_run_auto_backup_skips_remote_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = PathLayout(tmp_path / "home")
    layout.backups_dir.mkdir(parents=True)
    cfg_path = layout.config
    from octop.config import load_config
    from octop.infra.backup.auto import persist_backup_config

    load_config(cfg_path)
    persist_backup_config(cfg_path, BackupConfig(remote_enabled=False))

    server = MagicMock()
    server.paths = layout
    server.services = MagicMock()
    server.services.db = MagicMock()
    server.services.config.database = MagicMock()
    server.services.audit_repo.write = MagicMock()
    server.app_runtime = MagicMock()
    server.app_runtime.agent_registry.list_rows.return_value = []

    monkeypatch.setattr(
        auto_mod,
        "create_and_store_auto_backup",
        lambda **_k: (_entry(), []),
    )
    resolve = MagicMock(return_value=None)
    monkeypatch.setattr(auto_mod, "resolve_remote_engine", resolve)

    out = await auto_mod.run_auto_backup(server)
    assert out is not None
    resolve.assert_called_once()


@pytest.mark.asyncio
async def test_run_auto_backup_fails_closed_on_remote_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = PathLayout(tmp_path / "home")
    layout.backups_dir.mkdir(parents=True)
    (layout.backups_dir / "octop-auto-backup-20260101T000000Z.tar.gz").write_bytes(b"archive")
    cfg_path = layout.config
    from octop.config import load_config
    from octop.infra.backup.auto import persist_backup_config

    load_config(cfg_path)
    persist_backup_config(
        cfg_path, BackupConfig(remote_enabled=True, remote_backend_id=1, retention_count=3)
    )

    server = MagicMock()
    server.paths = layout
    server.services = MagicMock()
    server.services.db = MagicMock()
    server.services.config.database = MagicMock()
    server.services.audit_repo.write = MagicMock()
    server.services.storage_backend_repo.get = MagicMock()
    server.app_runtime = MagicMock()
    server.app_runtime.agent_registry.list_rows.return_value = []

    monkeypatch.setattr(
        auto_mod,
        "create_and_store_auto_backup",
        lambda **_k: (_entry(), ["old.tar.gz"]),
    )

    engine = MagicMock()
    engine.mirror = AsyncMock(return_value=MirrorResult(status="remote_failed", reason="http 500"))
    engine.prune_auto = AsyncMock(return_value=[])
    monkeypatch.setattr(auto_mod, "resolve_remote_engine", MagicMock(return_value=engine))

    with pytest.raises(OctopError) as exc_info:
        await auto_mod.run_auto_backup(server)
    assert exc_info.value.code == ErrorCode.BACKUP_REMOTE_FAILED
    engine.prune_auto.assert_not_awaited()
    # Local archive must remain for retry.
    assert (layout.backups_dir / "octop-auto-backup-20260101T000000Z.tar.gz").is_file()


@pytest.mark.asyncio
async def test_run_auto_backup_prunes_remote_after_remote_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = PathLayout(tmp_path / "home")
    layout.backups_dir.mkdir(parents=True)
    (layout.backups_dir / "octop-auto-backup-20260101T000000Z.tar.gz").write_bytes(b"archive")
    cfg_path = layout.config
    from octop.config import load_config
    from octop.infra.backup.auto import persist_backup_config

    load_config(cfg_path)
    persist_backup_config(
        cfg_path, BackupConfig(remote_enabled=True, remote_backend_id=1, retention_count=2)
    )

    server = MagicMock()
    server.paths = layout
    server.services = MagicMock()
    server.services.db = MagicMock()
    server.services.config.database = MagicMock()
    server.services.audit_repo.write = MagicMock()
    server.services.storage_backend_repo.get = MagicMock()
    server.app_runtime = MagicMock()
    server.app_runtime.agent_registry.list_rows.return_value = []

    monkeypatch.setattr(
        auto_mod,
        "create_and_store_auto_backup",
        lambda **_k: (_entry(), []),
    )
    engine = MagicMock()
    engine.mirror = AsyncMock(return_value=MirrorResult(status="remote_ok", reason="ok"))
    engine.prune_auto = AsyncMock(return_value=["old-remote.tar.gz"])
    monkeypatch.setattr(auto_mod, "resolve_remote_engine", MagicMock(return_value=engine))

    out = await auto_mod.run_auto_backup(server)
    assert out is not None
    engine.prune_auto.assert_awaited_once_with(keep=2, newest_status="remote_ok")


@pytest.mark.asyncio
async def test_create_backup_mirrors_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import backup as backup_router

    entry = _entry("octop-backup-20260101T000000Z.tar.gz")
    monkeypatch.setattr(backup_router, "_raise_if_backup_busy", lambda: None)
    monkeypatch.setattr(backup_router, "_agent_rows", lambda _s: [])
    monkeypatch.setattr(
        backup_router,
        "_create_and_store_manual_backup",
        lambda **_k: entry,
    )
    mirror = AsyncMock(
        return_value={"remote_status": "remote_ok", "remote_reason": "ok", "remote_pruned": []}
    )
    monkeypatch.setattr(backup_router, "_mirror_if_enabled", mirror)

    server = MagicMock()
    server.services = MagicMock()
    server.services.db = MagicMock()
    server.services.config.database = MagicMock()
    server.paths = MagicMock()

    result = await backup_router.create_backup(body=None, server=server)
    assert result["ok"] is True
    assert result["item"]["remote_status"] == "remote_ok"
    mirror.assert_awaited_once()
