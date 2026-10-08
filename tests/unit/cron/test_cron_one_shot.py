"""One-shot schedule lifecycle against real APScheduler and SQLite."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from apscheduler.events import EVENT_JOB_EXECUTED

from octop.infra.cron.manager import CronManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import RepoBundle


@pytest.fixture
def repos(tmp_path: Path):
    pool = SqlitePool(tmp_path / "cron.db")
    run_migrations(pool)
    bundle = RepoBundle.from_pool(pool)
    uid = bundle.user_repo.create(username="owner", password_hash="x", role="user")
    bundle.agent_repo.create(agent_id="agent", user_id=uid, name="Agent")
    yield bundle, uid
    pool.close()


def _create(repos, *, trigger: str, task_type: str = "text") -> None:
    bundle, uid = repos
    bundle.cron_repo.create(
        cron_id="once",
        agent_id="agent",
        user_id=uid,
        trigger=trigger,
        prompt="Reminder",
        session_key="agent:dashboard:1:dm",
        task_type=task_type,
    )


def _manager(repos, delivery):
    manager = CronManager(gateway=MagicMock(), delivery_service=delivery, repos=repos[0])
    completed = asyncio.Event()
    manager._scheduler.add_listener(lambda _event: completed.set(), EVENT_JOB_EXECUTED)
    return manager, completed


async def _shutdown(manager):
    await manager.shutdown()
    # AsyncIOScheduler queues its shutdown on the loop.
    await asyncio.sleep(0)


@pytest.mark.asyncio
@pytest.mark.parametrize("rebuild", ["reload", "restart"])
@pytest.mark.parametrize("fails", [False, True])
@pytest.mark.parametrize("task_type", ["text", "agent"])
async def test_one_shot_is_consumed_before_reload_or_restart(repos, rebuild, fails, task_type):
    _create(repos, trigger="date:" + datetime.now(UTC).isoformat(), task_type=task_type)
    delivery = MagicMock(deliver=AsyncMock(side_effect=RuntimeError("failed") if fails else None))
    manager, completed = _manager(repos, delivery)
    await manager.boot()
    try:
        await asyncio.wait_for(completed.wait(), timeout=5)
        row = repos[0].cron_repo.get("once")
        assert row.enabled == 0
        assert row.to_public_dict()["enabled"] is False
        assert row.last_status == ("error" if fails else "ok")
        assert manager._scheduler.get_job("once") is None
        if rebuild == "reload":
            await manager.reload_from_db()
        else:
            await _shutdown(manager)
            manager, _ = _manager(repos, delivery)
            await manager.boot()
        assert manager._scheduler.get_job("once") is None
        delivery.deliver.assert_awaited_once()
        assert delivery.deliver.await_args.args[0].task_type == task_type
        audit = repos[0].audit_repo.query()
        assert [(entry.action, entry.target) for entry in audit] == [
            ("cron.run_failed" if fails else "cron.run_ok", "once")
        ]
    finally:
        await _shutdown(manager)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["trigger", "disable", "delete"])
async def test_queued_one_shot_does_not_override_new_configuration(repos, change):
    original = "date:" + (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    _create(repos, trigger=original)
    delivery = MagicMock(deliver=AsyncMock())
    manager, _ = _manager(repos, delivery)
    await manager.boot()
    try:
        queued_run = manager._scheduler.get_job("once").func
        if change == "trigger":
            future = "date:" + (datetime.now(UTC) + timedelta(hours=2)).isoformat()
            await manager.update("once", trigger=future)
        elif change == "disable":
            await manager.update("once", enabled=0)
        else:
            await manager.delete("once")
        # APScheduler may already have queued the previous callable before an edit.
        await queued_run()
        delivery.deliver.assert_not_awaited()
        if change == "trigger":
            row = repos[0].cron_repo.get("once")
            assert row.enabled == 1
            assert row.trigger == future
            assert manager._scheduler.get_job("once") is not None
    finally:
        await _shutdown(manager)


@pytest.mark.asyncio
async def test_manual_run_preserves_future_one_shot(repos):
    _create(
        repos,
        trigger="date:" + (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )
    delivery = MagicMock(deliver=AsyncMock())
    manager, completed = _manager(repos, delivery)
    await manager.boot()
    try:
        await manager.run_now("once", wait=True)
        assert repos[0].cron_repo.get("once").enabled == 1
        assert manager._scheduler.get_job("once") is not None
        # Advance the queued run rather than waiting an hour.
        manager._scheduler.modify_job("once", next_run_time=datetime.now(UTC))
        await asyncio.wait_for(completed.wait(), timeout=5)
        assert repos[0].cron_repo.get("once").enabled == 0
        assert delivery.deliver.await_count == 2
    finally:
        await _shutdown(manager)


@pytest.mark.asyncio
async def test_inflight_one_shot_reload_and_schedule_edit(repos):
    _create(repos, trigger="date:" + datetime.now(UTC).isoformat())
    started, release = asyncio.Event(), asyncio.Event()

    async def deliver(_command):
        started.set()
        await release.wait()

    delivery = MagicMock(deliver=AsyncMock(side_effect=deliver))
    manager, completed = _manager(repos, delivery)
    await manager.boot()
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        assert repos[0].cron_repo.get("once").enabled == 0
        await manager.reload_from_db()
        assert manager._scheduler.get_job("once") is None
        future = "date:" + (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        await manager.update("once", trigger=future, enabled=1)
        release.set()
        await asyncio.wait_for(completed.wait(), timeout=5)
        row = repos[0].cron_repo.get("once")
        assert row.enabled == 1
        assert row.trigger == future
        assert manager._scheduler.get_job("once") is not None
        delivery.deliver.assert_awaited_once()
    finally:
        release.set()
        await _shutdown(manager)


@pytest.mark.asyncio
async def test_consumed_date_can_be_explicitly_reenabled(repos):
    _create(repos, trigger="date:" + datetime.now(UTC).isoformat())
    delivery = MagicMock(deliver=AsyncMock())
    manager, completed = _manager(repos, delivery)
    await manager.boot()
    try:
        await asyncio.wait_for(completed.wait(), timeout=5)
        assert repos[0].cron_repo.get("once").enabled == 0
        completed.clear()
        await manager.update("once", enabled=1)
        await asyncio.wait_for(completed.wait(), timeout=5)
        assert repos[0].cron_repo.get("once").enabled == 0
        assert delivery.deliver.await_count == 2
    finally:
        await _shutdown(manager)


@pytest.mark.asyncio
async def test_failed_one_shot_can_be_retried_manually_without_rescheduling(repos):
    _create(repos, trigger="date:" + datetime.now(UTC).isoformat())
    delivery = MagicMock(deliver=AsyncMock(side_effect=RuntimeError("failed")))
    manager, completed = _manager(repos, delivery)
    await manager.boot()
    try:
        await asyncio.wait_for(completed.wait(), timeout=5)
        assert repos[0].cron_repo.get("once").enabled == 0
        assert repos[0].cron_repo.get("once").last_status == "error"
        delivery.deliver.side_effect = None
        await manager.run_now("once", wait=True)
        assert repos[0].cron_repo.get("once").enabled == 0
        assert repos[0].cron_repo.get("once").last_status == "ok"
        await manager.reload_from_db()
        assert manager._scheduler.get_job("once") is None
        assert delivery.deliver.await_count == 2
    finally:
        await _shutdown(manager)


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", ["interval:3600", "cron:0 0 * * *"])
async def test_recurring_scheduled_runs_remain_enabled(repos, trigger):
    _create(repos, trigger=trigger)
    delivery = MagicMock(deliver=AsyncMock())
    manager, completed = _manager(repos, delivery)
    await manager.boot()
    try:
        manager._scheduler.modify_job("once", next_run_time=datetime.now(UTC))
        await asyncio.wait_for(completed.wait(), timeout=5)
        assert repos[0].cron_repo.get("once").enabled == 1
        assert manager._scheduler.get_job("once") is not None
        delivery.deliver.assert_awaited_once()
    finally:
        await _shutdown(manager)
