"""tests/unit/test_cron_job.py — tests for the gateway-based CronJob."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.cron.job import CronJob
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.audit import AuditRepo
from octop.infra.db.repos.cron import CronJobRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.threads import ThreadRegistry


@pytest.fixture
def setup(tmp_path: Path):
    db = SqlitePool(tmp_path / "x.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="bot")
    cron_repo = CronJobRepo(db)
    session_key = ThreadRegistry.make_key(
        agent_id="a1",
        channel_type="cron",
        channel_subject_id="j1",
        channel_chat_type=ThreadRegistry.CHAT_TYPE_DM,
    )
    SessionRepo(db).upsert(
        session_key=session_key,
        agent_id="a1",
        user_id=1,
        channel_type="cron",
        chat_type=ThreadRegistry.CHAT_TYPE_DM,
        thread_id="thr_seed",
        channel_subject_id="j1",
        channel_chat_type=ThreadRegistry.CHAT_TYPE_DM,
        channel_metadata={"channel_type": "cron", "user_id": 1},
    )
    cid = cron_repo.create(
        cron_id="j1",
        agent_id="a1",
        user_id=1,
        trigger="interval:60",
        prompt="say hi",
        session_key=session_key,
    )
    audit = AuditRepo(db)
    return cron_repo, audit, cid, session_key


def _job(
    *,
    cron_repo: CronJobRepo,
    audit: AuditRepo,
    cid: str,
    session_key: str,
    gateway: MagicMock,
    fresh_thread: bool = False,
    task_type: str = "agent",
) -> CronJob:
    return CronJob(
        cron_id=cid,
        agent_id="a1",
        prompt="hi",
        fresh_thread=fresh_thread,
        session_key=session_key,
        model=None,
        task_type=task_type,
        gateway=gateway,
        cron_repo=cron_repo,
        audit_repo=audit,
    )


@pytest.mark.asyncio
async def test_run_records_ok(setup) -> None:
    cron_repo, audit, cid, session_key = setup

    gateway = MagicMock()
    gateway.thread_registry = MagicMock()
    gateway.thread_registry.get_session = MagicMock(
        return_value=SessionRepo(cron_repo._db).get(session_key)
    )
    gateway.thread_registry.reset_by_session_key = AsyncMock(return_value="thr_new")
    gateway.push_text_from_session = AsyncMock()

    job = _job(cron_repo=cron_repo, audit=audit, cid=cid, session_key=session_key, gateway=gateway)
    await job.run()
    row = cron_repo.get(cid)
    assert row.last_status == "ok"
    assert row.last_run_at is not None


@pytest.mark.asyncio
async def test_run_uses_session_key(setup) -> None:
    cron_repo, audit, cid, session_key = setup

    gateway = MagicMock()
    gateway.thread_registry = MagicMock()
    gateway.thread_registry.get_session = MagicMock(
        return_value=SessionRepo(cron_repo._db).get(session_key)
    )
    gateway.push_text_from_session = AsyncMock()

    job = _job(cron_repo=cron_repo, audit=audit, cid=cid, session_key=session_key, gateway=gateway)
    await job.run()

    args = gateway.push_text_from_session.call_args
    assert args.args[0] == "a1"
    assert args.args[1] == session_key
    assert args.args[2] == "hi"
    assert args.kwargs["task_type"] == "agent"


@pytest.mark.asyncio
async def test_run_passes_task_type(setup) -> None:
    cron_repo, audit, cid, session_key = setup

    gateway = MagicMock()
    gateway.thread_registry = MagicMock()
    gateway.thread_registry.get_session = MagicMock(
        return_value=SessionRepo(cron_repo._db).get(session_key)
    )
    gateway.push_text_from_session = AsyncMock()

    job = _job(
        cron_repo=cron_repo,
        audit=audit,
        cid=cid,
        session_key=session_key,
        gateway=gateway,
        task_type="text",
    )
    await job.run()
    assert gateway.push_text_from_session.call_args.kwargs["task_type"] == "text"


@pytest.mark.asyncio
async def test_run_records_error_on_failure(setup) -> None:
    cron_repo, audit, cid, session_key = setup

    gateway = MagicMock()
    gateway.thread_registry = MagicMock()
    gateway.thread_registry.get_session = MagicMock(
        return_value=SessionRepo(cron_repo._db).get(session_key)
    )
    gateway.push_text_from_session = AsyncMock(side_effect=RuntimeError("nope"))

    job = _job(cron_repo=cron_repo, audit=audit, cid=cid, session_key=session_key, gateway=gateway)
    await job.run()
    row = cron_repo.get(cid)
    assert row.last_status == "error"
    assert row.last_error == "nope"
    rows = audit.query(action="cron.run_failed")
    assert rows


@pytest.mark.asyncio
async def test_fresh_thread_resets_on_run(setup) -> None:
    cron_repo, audit, cid, session_key = setup

    gateway = MagicMock()
    gateway.thread_registry = MagicMock()
    gateway.thread_registry.get_session = MagicMock(
        return_value=SessionRepo(cron_repo._db).get(session_key)
    )
    gateway.thread_registry.reset_by_session_key = AsyncMock(return_value="thr_fresh")
    gateway.push_text_from_session = AsyncMock()

    job = _job(
        cron_repo=cron_repo,
        audit=audit,
        cid=cid,
        session_key=session_key,
        gateway=gateway,
        fresh_thread=True,
    )
    await job.run()
    gateway.thread_registry.reset_by_session_key.assert_called_once_with(session_key)


@pytest.mark.asyncio
async def test_from_row_reads_persisted_session_key(setup) -> None:
    cron_repo, audit, cid, session_key = setup
    row = cron_repo.get(cid)
    assert row is not None

    gateway = MagicMock()
    job = CronJob.from_row(row, gateway=gateway, cron_repo=cron_repo, audit_repo=audit)
    assert job._session_key == session_key
    assert job._task_type == "agent"
