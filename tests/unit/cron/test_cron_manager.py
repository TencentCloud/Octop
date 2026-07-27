"""tests/unit/test_cron_manager.py

Unit tests for CronManager.  APScheduler and Gateway are patched out so no
real async tasks or LLM calls are made.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octop.config import OctopConfig
from octop.infra.cron.manager import CronManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.paths import PathLayout
from octop.infra.utils.ulid import new_ulid


def _cron_session_key(agent_id: str, cron_id: str) -> str:
    return ThreadRegistry.make_key(
        agent_id=agent_id,
        channel_type="cron",
        channel_subject_id=cron_id,
        channel_chat_type=ThreadRegistry.CHAT_TYPE_DM,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_services(tmp_path: Path):
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())


def _make_agent(
    services,
    *,
    user_id: int | None = None,
    name: str = "test-agent",
) -> tuple[str, int]:
    """Insert agent + owner user; return (agent_id, user_id)."""
    uid = user_id
    if uid is None:
        uid = services.repos.user_repo.create(
            username=f"u-{new_ulid()}",
            password_hash="x",
            role="user",
        )
    aid = new_ulid()
    services.repos.agent_repo.create(agent_id=aid, user_id=uid, name=name)
    return aid, uid


def _make_gateway() -> MagicMock:
    gw = MagicMock()
    gw.send = AsyncMock(return_value=_aiter([]))
    gw.thread_registry = MagicMock()
    gw.thread_registry.get_session = MagicMock(return_value=None)
    gw.thread_registry.get_or_create_by_key = AsyncMock(return_value="thr_mock")
    return gw


async def _aiter(items):
    for item in items:
        yield item


def _make_manager(services, *, gateway: MagicMock | None = None) -> CronManager:
    gw = gateway or _make_gateway()
    mgr = CronManager(gateway=gw, repos=services.repos, timezone="UTC")
    # Replace real APScheduler with a mock to avoid background threads
    fake_scheduler = MagicMock()
    fake_scheduler.running = False
    fake_scheduler.get_job = MagicMock(return_value=None)
    mgr._scheduler = fake_scheduler
    return mgr


def _cron_id() -> str:
    return new_ulid()


# ---------------------------------------------------------------------------
# boot() / shutdown()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_boot_starts_scheduler(tmp_path: Path) -> None:
    """boot() calls scheduler.start()."""
    services = _make_services(tmp_path)
    mgr = _make_manager(services)

    await mgr.boot()

    mgr._scheduler.start.assert_called_once()


@pytest.mark.asyncio
async def test_boot_schedules_enabled_jobs(tmp_path: Path) -> None:
    """boot() calls scheduler.add_job() for every enabled cron row."""
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)

    for _ in range(2):
        cid = _cron_id()
        services.repos.cron_repo.create(
            cron_id=cid,
            agent_id=aid,
            user_id=uid,
            trigger="interval:60",
            prompt="hello",
            session_key=_cron_session_key(aid, cid),
        )

    await mgr.boot()

    assert mgr._scheduler.add_job.call_count == 2


@pytest.mark.asyncio
async def test_boot_skips_disabled_jobs(tmp_path: Path) -> None:
    """boot() must not schedule jobs that have enabled=0."""
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    cid = _cron_id()
    services.repos.cron_repo.create(
        cron_id=cid,
        agent_id=aid,
        user_id=uid,
        trigger="interval:60",
        prompt="hi",
        session_key=_cron_session_key(aid, cid),
    )
    services.repos.cron_repo.update(cid, enabled=False)

    mgr = _make_manager(services)
    await mgr.boot()

    mgr._scheduler.add_job.assert_not_called()


@pytest.mark.asyncio
async def test_shutdown_stops_scheduler(tmp_path: Path) -> None:
    """shutdown() calls scheduler.shutdown() when running."""
    services = _make_services(tmp_path)
    mgr = _make_manager(services)
    mgr._scheduler.running = True

    await mgr.shutdown()

    mgr._scheduler.shutdown.assert_called_once_with(wait=False)


@pytest.mark.asyncio
async def test_shutdown_noop_when_not_running(tmp_path: Path) -> None:
    """shutdown() is a no-op when the scheduler is already stopped."""
    services = _make_services(tmp_path)
    mgr = _make_manager(services)
    mgr._scheduler.running = False

    await mgr.shutdown()

    mgr._scheduler.shutdown.assert_not_called()


# ---------------------------------------------------------------------------
# create()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_persists_row(tmp_path: Path) -> None:
    """create() inserts a row into the DB and returns it."""
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    cid = _cron_id()

    row = await mgr.create(
        cron_id=cid,
        agent_id=aid,
        user_id=uid,
        trigger="cron:0 9 * * *",
        prompt="morning report",
    )

    assert row.cron_id == cid
    assert row.prompt == "morning report"
    assert row.agent_id == aid
    assert mgr.get(cid) is not None


@pytest.mark.asyncio
async def test_create_schedules_job(tmp_path: Path) -> None:
    """create() calls scheduler.add_job() for the new enabled row."""
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)

    await mgr.create(
        cron_id=_cron_id(),
        agent_id=aid,
        user_id=uid,
        trigger="interval:30",
        prompt="ping",
    )

    mgr._scheduler.add_job.assert_called_once()


@pytest.mark.asyncio
async def test_create_writes_audit_entry(tmp_path: Path) -> None:
    """create() writes a cron.create audit log entry."""
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    cid = _cron_id()

    await mgr.create(
        cron_id=cid,
        agent_id=aid,
        user_id=uid,
        trigger="interval:60",
        prompt="check",
    )

    audit = services.repos.audit_repo.query(action="cron.create", limit=5)
    assert any(a.target == cid for a in audit)


@pytest.mark.asyncio
async def test_create_rejects_invalid_trigger(tmp_path: Path) -> None:
    """create() raises OctopError for a malformed trigger spec."""
    from octop.infra.errors import OctopError  # noqa: PLC0415

    services = _make_services(tmp_path)
    mgr = _make_manager(services)
    _aid, uid = _make_agent(services)

    with pytest.raises(OctopError):
        await mgr.create(
            cron_id=_cron_id(),
            agent_id="whatever",
            user_id=uid,
            trigger="not-valid-spec",
            prompt="x",
        )


@pytest.mark.asyncio
async def test_create_stores_fresh_thread(tmp_path: Path) -> None:
    """create() persists fresh_thread correctly."""
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    cid = _cron_id()

    row = await mgr.create(
        cron_id=cid,
        agent_id=aid,
        user_id=uid,
        trigger="interval:120",
        prompt="work",
        fresh_thread=True,
    )

    assert bool(row.fresh_thread) is True


# ---------------------------------------------------------------------------
# get() / list_by_agent() / list_all()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    mgr = _make_manager(services)

    assert mgr.get("nonexistent") is None


@pytest.mark.asyncio
async def test_get_returns_created_row(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    cid = _cron_id()

    await mgr.create(cron_id=cid, agent_id=aid, user_id=uid, trigger="interval:10", prompt="y")

    row = mgr.get(cid)
    assert row is not None
    assert row.cron_id == cid


@pytest.mark.asyncio
async def test_list_by_agent_returns_only_that_agents_jobs(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    aid_a, uid = _make_agent(services)
    aid_b, _ = _make_agent(services, user_id=uid, name="test-agent-b")
    mgr = _make_manager(services)

    await mgr.create(
        cron_id=_cron_id(),
        agent_id=aid_a,
        user_id=uid,
        trigger="interval:60",
        prompt="x",
    )
    await mgr.create(
        cron_id=_cron_id(),
        agent_id=aid_b,
        user_id=uid,
        trigger="interval:60",
        prompt="x",
    )

    rows_a = mgr.list_by_agent(aid_a)
    rows_b = mgr.list_by_agent(aid_b)

    assert len(rows_a) == 1
    assert rows_a[0].agent_id == aid_a
    assert len(rows_b) == 1


@pytest.mark.asyncio
async def test_list_all_returns_all_jobs(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    mgr = _make_manager(services)

    for i in range(3):
        aid, uid = _make_agent(services, name=f"ag-{i}")
        await mgr.create(
            cron_id=_cron_id(),
            agent_id=aid,
            user_id=uid,
            trigger="interval:60",
            prompt="p",
        )

    assert len(mgr.list_all()) == 3


@pytest.mark.asyncio
async def test_list_by_agent_exclude_disabled(tmp_path: Path) -> None:
    """list_by_agent() with include_disabled=False hides disabled rows."""
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    cid = _cron_id()

    await mgr.create(
        cron_id=cid,
        agent_id=aid,
        user_id=uid,
        trigger="interval:10",
        prompt="x",
    )
    await mgr.update(cid, enabled=0)

    rows = mgr.list_by_agent(aid, include_disabled=False)
    assert rows == []


# ---------------------------------------------------------------------------
# update()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_persists_prompt_change(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    cid = _cron_id()
    await mgr.create(cron_id=cid, agent_id=aid, user_id=uid, trigger="interval:10", prompt="p")

    updated = await mgr.update(cid, prompt="new prompt")

    assert updated.prompt == "new prompt"
    assert mgr.get(cid).prompt == "new prompt"


@pytest.mark.asyncio
async def test_update_reschedules_on_trigger_change(tmp_path: Path) -> None:
    """update() with a new trigger removes old job and re-adds."""
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    cid = _cron_id()
    await mgr.create(cron_id=cid, agent_id=aid, user_id=uid, trigger="interval:10", prompt="p")
    mgr._scheduler.get_job = MagicMock(return_value=MagicMock())
    mgr._scheduler.add_job.reset_mock()
    mgr._scheduler.remove_job.reset_mock()

    await mgr.update(cid, trigger="interval:120")

    mgr._scheduler.remove_job.assert_called_with(cid)
    mgr._scheduler.add_job.assert_called_once()


@pytest.mark.asyncio
async def test_update_unschedules_when_disabled(tmp_path: Path) -> None:
    """update(enabled=0) removes the APScheduler job."""
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    cid = _cron_id()
    await mgr.create(cron_id=cid, agent_id=aid, user_id=uid, trigger="interval:10", prompt="p")
    mgr._scheduler.get_job = MagicMock(return_value=MagicMock())
    mgr._scheduler.remove_job.reset_mock()
    mgr._scheduler.add_job.reset_mock()

    await mgr.update(cid, enabled=0)

    mgr._scheduler.remove_job.assert_called_with(cid)
    mgr._scheduler.add_job.assert_not_called()


@pytest.mark.asyncio
async def test_update_reschedules_when_re_enabled(tmp_path: Path) -> None:
    """update(enabled=1) on a disabled job re-adds it to the scheduler."""
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    cid = _cron_id()
    await mgr.create(cron_id=cid, agent_id=aid, user_id=uid, trigger="interval:10", prompt="p")
    await mgr.update(cid, enabled=0)
    mgr._scheduler.add_job.reset_mock()
    mgr._scheduler.get_job = MagicMock(return_value=None)

    await mgr.update(cid, enabled=1)

    mgr._scheduler.add_job.assert_called_once()


@pytest.mark.asyncio
async def test_update_raises_for_unknown_id(tmp_path: Path) -> None:
    from octop.infra.errors import OctopError  # noqa: PLC0415

    services = _make_services(tmp_path)
    mgr = _make_manager(services)

    with pytest.raises(OctopError):
        await mgr.update("no-such-id", prompt="x")


@pytest.mark.asyncio
async def test_update_rejects_invalid_trigger(tmp_path: Path) -> None:
    from octop.infra.errors import OctopError  # noqa: PLC0415

    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    cid = _cron_id()
    await mgr.create(cron_id=cid, agent_id=aid, user_id=uid, trigger="interval:10", prompt="p")

    with pytest.raises(OctopError):
        await mgr.update(cid, trigger="bad::spec")


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_from_db(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    cid = _cron_id()
    await mgr.create(cron_id=cid, agent_id=aid, user_id=uid, trigger="interval:10", prompt="p")

    await mgr.delete(cid)

    assert mgr.get(cid) is None


@pytest.mark.asyncio
async def test_delete_unschedules_job(tmp_path: Path) -> None:
    """delete() calls scheduler.remove_job when the job is registered."""
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    cid = _cron_id()
    await mgr.create(cron_id=cid, agent_id=aid, user_id=uid, trigger="interval:10", prompt="p")
    mgr._scheduler.get_job = MagicMock(return_value=MagicMock())
    mgr._scheduler.remove_job.reset_mock()

    await mgr.delete(cid)

    mgr._scheduler.remove_job.assert_called_with(cid)


@pytest.mark.asyncio
async def test_delete_writes_audit_entry(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    cid = _cron_id()
    await mgr.create(cron_id=cid, agent_id=aid, user_id=uid, trigger="interval:10", prompt="p")

    await mgr.delete(cid)

    audit = services.repos.audit_repo.query(action="cron.delete", limit=5)
    assert any(a.target == cid for a in audit)


# ---------------------------------------------------------------------------
# run_now()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_now_raises_for_unknown(tmp_path: Path) -> None:
    from octop.infra.errors import OctopError  # noqa: PLC0415

    services = _make_services(tmp_path)
    mgr = _make_manager(services)

    with pytest.raises(OctopError):
        await mgr.run_now("no-such-id")


@pytest.mark.asyncio
async def test_run_now_fires_job(tmp_path: Path) -> None:
    """run_now() schedules an immediate async task via ensure_future."""
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    gateway = _make_gateway()
    mgr = _make_manager(services, gateway=gateway)
    cid = _cron_id()
    await mgr.create(
        cron_id=cid,
        agent_id=aid,
        user_id=uid,
        trigger="interval:3600",
        prompt="run",
    )

    with patch("octop.infra.cron.manager.asyncio.ensure_future") as mock_ef:
        await mgr.run_now(cid)
        mock_ef.assert_called_once()
        coro = mock_ef.call_args[0][0]
        coro.close()  # clean up without awaiting


# ---------------------------------------------------------------------------
# _schedule() edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_skips_invalid_trigger_gracefully(tmp_path: Path) -> None:
    """_schedule() logs a warning but does not raise for bad trigger specs."""
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)

    cid = _cron_id()
    services.repos.cron_repo.create(
        cron_id=cid,
        agent_id=aid,
        user_id=uid,
        trigger="garbage:???",
        prompt="x",
        session_key=_cron_session_key(aid, cid),
    )
    row = services.repos.cron_repo.get(cid)

    mgr._schedule(row)  # must not raise

    mgr._scheduler.add_job.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_replaces_existing_job(tmp_path: Path) -> None:
    """_schedule() removes the old APScheduler job before adding the new one."""
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    mgr._scheduler.get_job = MagicMock(return_value=MagicMock())

    cid = _cron_id()
    services.repos.cron_repo.create(
        cron_id=cid,
        agent_id=aid,
        user_id=uid,
        trigger="interval:5",
        prompt="x",
        session_key=_cron_session_key(aid, cid),
    )
    row = services.repos.cron_repo.get(cid)
    mgr._schedule(row)

    mgr._scheduler.remove_job.assert_called_with(cid)
    mgr._scheduler.add_job.assert_called_once()
