"""tests/unit/test_repo_cron.py"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.cron import CronJobRepo, CronJobRow
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.ulid import new_ulid


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "x.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def agent_id(db: SqlitePool) -> str:
    uid = UserRepo(db).create(username="alice", password_hash="h", role="admin")
    aid = new_ulid()
    AgentRepo(db).create(agent_id=aid, user_id=uid, name="bot")
    return aid


@pytest.fixture
def user_id(db: SqlitePool) -> int:
    return UserRepo(db).get_by_username("alice").id


@pytest.fixture
def repo(db: SqlitePool) -> CronJobRepo:
    return CronJobRepo(db)


def _session_key(agent_id: str, user_id: int) -> str:
    return ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=user_id)


def test_create_and_get(repo: CronJobRepo, agent_id: str, user_id: int):
    cid = new_ulid()
    repo.create(
        cron_id=cid,
        agent_id=agent_id,
        user_id=user_id,
        trigger="0 9 * * *",
        prompt="run report",
        session_key=_session_key(agent_id, user_id),
    )
    row = repo.get(cid)
    assert isinstance(row, CronJobRow)
    assert row.cron_id == cid
    assert row.trigger == "0 9 * * *"
    assert row.enabled == 1
    assert row.task_type == "agent"
    assert row.last_run_at is None


def test_create_with_task_type(repo: CronJobRepo, agent_id: str, user_id: int):
    cid = new_ulid()
    repo.create(
        cron_id=cid,
        agent_id=agent_id,
        user_id=user_id,
        trigger="0 9 * * *",
        prompt="push only",
        session_key=_session_key(agent_id, user_id),
        task_type="text",
    )
    row = repo.get(cid)
    assert row is not None
    assert row.task_type == "text"
    repo.update(cid, task_type="agent")
    row = repo.get(cid)
    assert row is not None
    assert row.task_type == "agent"


def test_set_run_status(repo: CronJobRepo, agent_id: str, user_id: int):
    cid = new_ulid()
    repo.create(
        cron_id=cid,
        agent_id=agent_id,
        user_id=user_id,
        trigger="0 9 * * *",
        prompt="run report",
        session_key=_session_key(agent_id, user_id),
    )
    ts = int(time.time())
    repo.set_run_status(cid, ts=ts, status="ok")
    row = repo.get(cid)
    assert row.last_run_at == ts
    assert row.last_status == "ok"
    assert row.last_error is None

    repo.set_run_status(cid, ts=ts + 1, status="error", error="boom")
    row = repo.get(cid)
    assert row.last_status == "error"
    assert row.last_error == "boom"


def test_list_by_agent(repo: CronJobRepo, agent_id: str, user_id: int):
    sk = _session_key(agent_id, user_id)
    repo.create(
        cron_id=new_ulid(),
        agent_id=agent_id,
        user_id=user_id,
        trigger="* * * * *",
        prompt="p1",
        session_key=sk,
    )
    repo.create(
        cron_id=new_ulid(),
        agent_id=agent_id,
        user_id=user_id,
        trigger="* * * * *",
        prompt="p2",
        session_key=sk,
    )
    rows = repo.list_by_agent(agent_id)
    assert len(rows) == 2


def test_update_partial(repo: CronJobRepo, agent_id: str, user_id: int):
    cid = new_ulid()
    repo.create(
        cron_id=cid,
        agent_id=agent_id,
        user_id=user_id,
        trigger="0 9 * * *",
        prompt="run report",
        session_key=_session_key(agent_id, user_id),
    )
    repo.update(cid, trigger="0 10 * * *", enabled=False)
    row = repo.get(cid)
    assert row.trigger == "0 10 * * *"
    assert row.enabled == 0
    assert row.prompt == "run report"


def test_delete(repo: CronJobRepo, agent_id: str, user_id: int):
    cid = new_ulid()
    repo.create(
        cron_id=cid,
        agent_id=agent_id,
        user_id=user_id,
        trigger="0 9 * * *",
        prompt="run report",
        session_key=_session_key(agent_id, user_id),
    )
    repo.delete(cid)
    assert repo.get(cid) is None
