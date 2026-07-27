"""Unit tests for admin backup restore rehydrate."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.api.routers import backup as backup_router


@pytest.mark.asyncio
async def test_restore_backup_file_rehydrates_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After restore, sync providers into harness so experts can start without process restart."""
    on_provider_changed = AsyncMock()
    restored: dict[str, Any] = {
        "schema_version": 1,
        "octop_version": "0.0.0",
        "agents": 1,
        "workspace_files": 2,
        "restore_config": True,
    }

    monkeypatch.setattr(backup_router, "normalize_backup_filename", lambda name: name)
    monkeypatch.setattr(backup_router, "read_backup_file", lambda *_a, **_k: b"fake-archive")
    monkeypatch.setattr(
        backup_router,
        "restore_system_backup",
        lambda *_a, **_k: restored,
    )

    server = MagicMock()
    server.services = MagicMock()
    server.services.db = MagicMock()
    server.services.config.database = MagicMock()
    server.services.audit_repo.write = MagicMock()
    server.paths = MagicMock()
    server.app_runtime = MagicMock()
    server.app_runtime.agent_registry.on_provider_changed = on_provider_changed

    result = await backup_router.restore_backup_file(
        filename="octop-backup.tar.gz",
        restore_config=True,
        _=None,
        server=server,
    )

    on_provider_changed.assert_awaited_once_with()
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
    monkeypatch.setattr(backup_router, "read_backup_file", lambda *_a, **_k: b"fake-archive")
    monkeypatch.setattr(
        backup_router,
        "restore_system_backup",
        lambda *_a, **_k: restored,
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
        _=None,
        server=server,
    )

    assert result["ok"] is True
