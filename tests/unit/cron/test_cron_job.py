"""tests/unit/test_cron_job.py — CronJob bookkeeping around CronDeliveryService."""

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
    delivery_service: MagicMock,
    fresh_thread: bool = False,
    task_type: str = "agent",
    mcp_servers: list[str] | None = None,
) -> CronJob:
    return CronJob(
        cron_id=cid,
        name="say hi",
        agent_id="a1",
        prompt="hi",
        fresh_thread=fresh_thread,
        session_key=session_key,
        model=None,
        task_type=task_type,
        mcp_servers=mcp_servers,
        user_id=1,
        delivery_service=delivery_service,
        cron_repo=cron_repo,
        audit_repo=audit,
    )


@pytest.mark.asyncio
async def test_run_records_ok(setup) -> None:
    cron_repo, audit, cid, session_key = setup
    delivery = MagicMock()
    delivery.deliver = AsyncMock()

    job = _job(
        cron_repo=cron_repo,
        audit=audit,
        cid=cid,
        session_key=session_key,
        delivery_service=delivery,
    )
    await job.run()
    row = cron_repo.get(cid)
    assert row.last_status == "ok"
    assert row.last_run_at is not None
    delivery.deliver.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_passes_delivery_command(setup) -> None:
    cron_repo, audit, cid, session_key = setup
    delivery = MagicMock()
    delivery.deliver = AsyncMock()

    job = _job(
        cron_repo=cron_repo,
        audit=audit,
        cid=cid,
        session_key=session_key,
        delivery_service=delivery,
        mcp_servers=["github__1"],
        task_type="text",
        fresh_thread=True,
    )
    await job.run()

    command = delivery.deliver.await_args.args[0]
    assert command.cron_id == cid
    assert command.cron_name == "say hi"
    assert command.agent_id == "a1"
    assert command.user_id == 1
    assert command.session_key == session_key
    assert command.prompt == "hi"
    assert command.fresh_thread is True
    assert command.task_type == "text"
    assert command.mcp_servers == ("github__1",)


@pytest.mark.asyncio
async def test_run_records_error_on_failure(setup) -> None:
    cron_repo, audit, cid, session_key = setup
    delivery = MagicMock()
    delivery.deliver = AsyncMock(side_effect=RuntimeError("nope"))

    job = _job(
        cron_repo=cron_repo,
        audit=audit,
        cid=cid,
        session_key=session_key,
        delivery_service=delivery,
    )
    await job.run()
    row = cron_repo.get(cid)
    assert row.last_status == "error"
    assert row.last_error == "nope"
    rows = audit.query(action="cron.run_failed")
    assert rows


@pytest.mark.asyncio
async def test_from_row_reads_persisted_session_key(setup) -> None:
    cron_repo, audit, cid, session_key = setup
    row = cron_repo.get(cid)
    assert row is not None

    delivery = MagicMock()
    job = CronJob.from_row(
        row,
        delivery_service=delivery,
        cron_repo=cron_repo,
        audit_repo=audit,
    )
    assert job._session_key == session_key
    assert job._task_type == "agent"
    assert job._name == row.name
    assert job._user_id == 1
