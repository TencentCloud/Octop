"""tests/unit/cron/test_cron_agent_delete.py

An agent's schedules live in the process, not only in the ``cron_jobs`` table.
``cron_jobs.agent_id`` cascades with the agent row, so deleting an agent erases
the rows that are the only handle the API has on those schedules.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.cron.delivery import CronDeliveryService
from octop.infra.cron.manager import CronManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import SharedServices, build_shared_services
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.paths import PathLayout
from octop.infra.utils.ulid import new_ulid


def _make_services(tmp_path: Path) -> SharedServices:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())


class _FakeScheduler:
    """Tracks registered ids the way APScheduler does, so removals are meaningful."""

    def __init__(self) -> None:
        self.running = False
        self.ids: list[str] = []

    def start(self) -> None:
        self.running = True

    def get_job(self, job_id: str) -> object | None:
        return object() if job_id in self.ids else None

    def get_jobs(self) -> list[Any]:
        return [SimpleNamespace(id=job_id) for job_id in self.ids]

    def add_job(self, func: Any, **kwargs: Any) -> None:
        self.ids.append(str(kwargs["id"]))

    def remove_job(self, job_id: str) -> None:
        self.ids.remove(job_id)


def _make_cron_manager(services: SharedServices) -> CronManager:
    gw = MagicMock()
    mgr = CronManager(
        gateway=gw,
        delivery_service=CronDeliveryService(
            gateway=gw,
            agent_manager=MagicMock(),
            repos=services.repos,
        ),
        repos=services.repos,
        timezone="UTC",
    )
    fake_scheduler = _FakeScheduler()
    mgr._scheduler = fake_scheduler  # type: ignore[assignment]
    return mgr


def _make_agent_manager(services: SharedServices) -> AgentManager:
    harness_manager = MagicMock()
    harness_manager.aremove_agent = AsyncMock()
    manager = AgentManager(repos=services.repos, paths=services.paths)
    manager._harness_manager = harness_manager
    return manager


def _seed_agent_with_job(services: SharedServices) -> tuple[str, str]:
    uid = services.repos.user_repo.create(
        username=f"u-{new_ulid()}",
        password_hash="x",
        role="user",
    )
    aid = new_ulid()
    services.repos.agent_repo.create(agent_id=aid, user_id=uid, name="cron-owner")
    cid = new_ulid()
    services.repos.cron_repo.create(
        cron_id=cid,
        agent_id=aid,
        user_id=uid,
        trigger="interval:60",
        prompt="hello",
        session_key=ThreadRegistry.make_key(
            agent_id=aid,
            channel_type="cron",
            channel_subject_id=cid,
            channel_chat_type=ThreadRegistry.CHAT_TYPE_DM,
        ),
    )
    return aid, cid


@pytest.mark.asyncio
async def test_deleting_an_agent_unschedules_its_cron_jobs(tmp_path: Path) -> None:
    """The cascade deletes the rows, so the schedule must be dropped with them."""
    services = _make_services(tmp_path)
    aid, cid = _seed_agent_with_job(services)

    cron_manager = _make_cron_manager(services)
    await cron_manager.boot()
    assert cron_manager._scheduler.ids == [cid]

    manager = _make_agent_manager(services)
    manager.set_cron_manager(cron_manager)

    await manager.delete(aid)

    assert services.repos.cron_repo.get(cid) is None
    assert cron_manager._scheduler.ids == []
