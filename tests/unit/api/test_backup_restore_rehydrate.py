"""Unit tests for admin backup restore rehydrate and non-blocking paths."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.api.routers import backup as backup_router
from octop.infra.backup.auto import BACKUP_LOCK
from octop.infra.backup.store import BackupFileInfo
from octop.infra.errors import ErrorCode, OctopError


@pytest.mark.asyncio
async def test_restore_backup_file_rehydrates_providers_channels_and_cron(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After restore, sync providers/agents, channels, and cron without process restart."""
    on_provider_changed = AsyncMock()
    reload_channels = AsyncMock()
    reload_cron = AsyncMock()
    restored: dict[str, Any] = {
        "schema_version": 1,
        "octop_version": "0.0.0",
        "agents": 1,
        "workspace_files": 2,
        "restore_config": True,
    }

    monkeypatch.setattr(backup_router, "normalize_backup_filename", lambda name: name)
    monkeypatch.setattr(
        backup_router,
        "_restore_stored_backup",
        lambda **_k: restored,
    )

    server = MagicMock()
    server.services = MagicMock()
    server.services.db = MagicMock()
    server.services.config.database = MagicMock()
    server.services.audit_repo.write = MagicMock()
    server.paths = MagicMock()
    server.app_runtime = MagicMock()
    server.app_runtime.agent_registry.on_provider_changed = on_provider_changed
    server.app_runtime.gateway.reload_channels_from_db = reload_channels
    server.app_runtime.cron_manager.reload_from_db = reload_cron

    result = await backup_router.restore_backup_file(
        filename="octop-backup.tar.gz",
        restore_config=True,
        user=MagicMock(id=1, username="admin"),
        server=server,
    )

    on_provider_changed.assert_awaited_once_with()
    reload_channels.assert_awaited_once_with()
    reload_cron.assert_awaited_once_with()
    assert result["ok"] is True
    assert result["name"] == "octop-backup.tar.gz"
    assert result["agents"] == 1


@pytest.mark.asyncio
async def test_restore_backup_file_skips_rehydrate_without_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restored: dict[str, Any] = {
        "schema_version": 1,
        "octop_version": "0.0.0",
        "agents": 0,
        "workspace_files": 0,
        "restore_config": False,
    }
    monkeypatch.setattr(backup_router, "normalize_backup_filename", lambda name: name)
    monkeypatch.setattr(
        backup_router,
        "_restore_stored_backup",
        lambda **_k: restored,
    )

    server = MagicMock()
    server.services = MagicMock()
    server.services.db = MagicMock()
    server.services.config.database = MagicMock()
    server.services.audit_repo.write = MagicMock()
    server.paths = MagicMock()
    server.app_runtime = None

    result = await backup_router.restore_backup_file(
        filename="octop-backup.tar.gz",
        restore_config=False,
        user=MagicMock(id=1, username="admin"),
        server=server,
    )

    assert result["ok"] is True


@pytest.mark.asyncio
async def test_rehydrate_reloads_channels_and_cron_even_if_provider_rehydrate_fails() -> None:
    """Channel and cron reload must still run when agent rehydrate raises."""
    on_provider_changed = AsyncMock(side_effect=RuntimeError("provider boom"))
    reload_channels = AsyncMock()
    reload_cron = AsyncMock()

    server = MagicMock()
    server.app_runtime = MagicMock()
    server.app_runtime.agent_registry.on_provider_changed = on_provider_changed
    server.app_runtime.gateway.reload_channels_from_db = reload_channels
    server.app_runtime.cron_manager.reload_from_db = reload_cron

    await backup_router._rehydrate_runtime_after_restore(server)

    on_provider_changed.assert_awaited_once_with()
    reload_channels.assert_awaited_once_with()
    reload_cron.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_create_backup_offloads_to_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """Manual create must not run tar/sqlite work on the event loop."""
    entry = BackupFileInfo(
        name="octop-backup-20260101T000000Z.tar.gz",
        size=12,
        modified_at="2026-01-01T00:00:00+00:00",
        created_at="2026-01-01T00:00:00+00:00",
    )
    called: dict[str, Any] = {}

    def _fake_create(**kwargs: Any) -> BackupFileInfo:
        called.update(kwargs)
        return entry

    monkeypatch.setattr(backup_router, "_create_and_store_manual_backup", _fake_create)
    monkeypatch.setattr(backup_router, "_agent_rows", lambda _server: [])

    server = MagicMock()
    server.services = MagicMock()
    server.services.db = object()
    server.services.config.database = object()
    server.paths = object()
    server.app_runtime = MagicMock()

    result = await backup_router.create_backup(_=None, server=server)

    assert result == {"ok": True, "item": entry.to_dict()}
    assert called["pool"] is server.services.db


@pytest.mark.asyncio
async def test_create_backup_rejects_when_lock_held() -> None:
    await BACKUP_LOCK.acquire()
    try:
        with pytest.raises(OctopError) as exc_info:
            await backup_router.create_backup(_=None, server=MagicMock(services=MagicMock()))
        assert exc_info.value.code == ErrorCode.BACKUP_IN_PROGRESS
    finally:
        BACKUP_LOCK.release()


@pytest.mark.asyncio
async def test_restore_backup_rejects_when_lock_held(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backup_router, "normalize_backup_filename", lambda name: name)
    await BACKUP_LOCK.acquire()
    try:
        with pytest.raises(OctopError) as exc_info:
            await backup_router.restore_backup_file(
                filename="octop-backup.tar.gz",
                restore_config=True,
                user=MagicMock(id=1, username="admin"),
                server=MagicMock(services=MagicMock()),
            )
        assert exc_info.value.code == ErrorCode.BACKUP_IN_PROGRESS
    finally:
        BACKUP_LOCK.release()


@pytest.mark.asyncio
async def test_backup_status_reports_idle_and_busy() -> None:
    from octop.infra.backup.auto import hold_backup_lock

    idle = await backup_router.get_backup_status(_=None)
    assert idle == {"busy": False, "operation": None}

    async with hold_backup_lock("create"):
        busy = await backup_router.get_backup_status(_=None)
        assert busy == {"busy": True, "operation": "create"}
