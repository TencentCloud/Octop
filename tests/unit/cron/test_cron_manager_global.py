"""tests/unit/test_cron_manager_global.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from octop.config import OctopConfig
from octop.infra.cron.manager import CronManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.paths import PathLayout


def _make_services(tmp_path: Path):
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())


@pytest.mark.asyncio
async def test_boot_empty(tmp_path: Path) -> None:
    """Boot with no cron jobs should succeed silently."""
    services = _make_services(tmp_path)
    gateway = MagicMock()
    gateway.thread_registry = MagicMock()
    mgr = CronManager(gateway=gateway, repos=services.repos, timezone="UTC")
    mgr._scheduler = MagicMock()
    mgr._scheduler.get_job = MagicMock(return_value=None)
    await mgr.boot()
    mgr._scheduler.add_job.assert_not_called()
    await mgr.shutdown()


@pytest.mark.asyncio
async def test_add_and_remove(tmp_path: Path) -> None:
    """Add a cron row and verify it's scheduled, then remove it."""
    services = _make_services(tmp_path)
    uid = services.user_repo.create(username="admin", password_hash="x", role="admin")
    services.agent_repo.create(agent_id="a1", user_id=uid, name="Test Agent")
    services.cron_repo.create(
        cron_id="c1",
        agent_id="a1",
        user_id=uid,
        trigger="interval:3600",
        prompt="hello",
        session_key=ThreadRegistry.make_key(
            agent_id="a1",
            channel_type="cron",
            channel_subject_id="c1",
            channel_chat_type=ThreadRegistry.CHAT_TYPE_DM,
        ),
    )

    gateway = MagicMock()
    gateway.thread_registry = MagicMock()
    mgr = CronManager(gateway=gateway, repos=services.repos, timezone="UTC")
    mgr._scheduler = MagicMock()
    mgr._scheduler.get_job = MagicMock(return_value=None)
    await mgr.boot()
    mgr._scheduler.add_job.assert_called_once()

    await mgr.delete("c1")
    assert services.cron_repo.get("c1") is None
    await mgr.shutdown()
