"""Per-cron 24h token budget circuit breaker (#1014)."""

from __future__ import annotations

import asyncio
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
def env(tmp_path: Path):
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
    cron_repo.create(
        cron_id="j1",
        agent_id="a1",
        user_id=1,
        trigger="interval:60",
        prompt="say hi",
        session_key=session_key,
    )
    return cron_repo, AuditRepo(db), db, session_key


def _job(
    *,
    cron_repo: CronJobRepo,
    audit: AuditRepo,
    session_key: str,
    delivery: MagicMock,
    on_budget_exceeded: MagicMock | None = None,
) -> CronJob:
    return CronJob(
        cron_id="j1",
        name="say hi",
        agent_id="a1",
        prompt="hi",
        fresh_thread=False,
        session_key=session_key,
        model=None,
        task_type="agent",
        mcp_servers=None,
        user_id=1,
        delivery_service=delivery,
        cron_repo=cron_repo,
        audit_repo=audit,
        on_budget_exceeded=on_budget_exceeded,
    )


def _delivery_returning(tokens: int) -> MagicMock:
    delivery = MagicMock()
    delivery.deliver = AsyncMock(return_value=tokens)
    return delivery


def test_apply_token_budget_noop_without_budget(env) -> None:
    cron_repo, _audit, _db, _sk = env
    assert cron_repo.apply_token_budget("j1", run_tokens=1_000_000) is False
    row = cron_repo.get("j1")
    assert row is not None
    assert row.enabled == 1


def test_apply_token_budget_accumulates_then_disables(env) -> None:
    cron_repo, _audit, _db, _sk = env
    cron_repo.update("j1", token_budget_24h=1_500)

    assert cron_repo.apply_token_budget("j1", run_tokens=1_000) is False
    row = cron_repo.get("j1")
    assert row is not None
    assert row.budget_tokens_used == 1_000
    assert row.enabled == 1

    assert cron_repo.apply_token_budget("j1", run_tokens=600) is True
    row = cron_repo.get("j1")
    assert row is not None
    assert row.budget_tokens_used == 1_600
    assert row.enabled == 0


def test_apply_token_budget_window_expiry_resets(env) -> None:
    cron_repo, _audit, db, _sk = env
    cron_repo.update("j1", token_budget_24h=10_000)
    assert cron_repo.apply_token_budget("j1", run_tokens=9_000) is False

    # Backdate the window anchor one day; the next run starts a fresh window.
    with db.connect() as conn:
        conn.execute(
            "UPDATE cron_jobs SET budget_window_started_at = budget_window_started_at - 86401"
        )

    assert cron_repo.apply_token_budget("j1", run_tokens=500) is False
    row = cron_repo.get("j1")
    assert row is not None
    assert row.budget_tokens_used == 500
    assert row.enabled == 1


def test_apply_token_budget_unknown_job(env) -> None:
    cron_repo, _audit, _db, _sk = env
    assert cron_repo.apply_token_budget("nope", run_tokens=10) is False


@pytest.mark.asyncio
async def test_run_trips_budget_and_disables(env) -> None:
    cron_repo, audit, _db, session_key = env
    cron_repo.update("j1", token_budget_24h=1_000)

    from octop.infra.metrics import METRICS

    before = METRICS.snapshot()["cron_budget_exceeded_total"]
    on_budget = MagicMock()
    job = _job(
        cron_repo=cron_repo,
        audit=audit,
        session_key=session_key,
        delivery=_delivery_returning(1_200),
        on_budget_exceeded=on_budget,
    )

    await job.run()

    row = cron_repo.get("j1")
    assert row is not None
    assert row.last_status == "budget_exceeded"
    assert row.enabled == 0
    assert row.budget_tokens_used == 1_200
    assert [a.target for a in audit.query(action="cron.budget_exceeded")] == ["j1"]
    on_budget.assert_called_once_with("j1")
    assert METRICS.snapshot()["cron_budget_exceeded_total"] == before + 1


@pytest.mark.asyncio
async def test_run_within_budget_stays_enabled(env) -> None:
    cron_repo, audit, _db, session_key = env
    cron_repo.update("j1", token_budget_24h=10_000)

    job = _job(
        cron_repo=cron_repo,
        audit=audit,
        session_key=session_key,
        delivery=_delivery_returning(1_200),
    )
    await job.run()

    row = cron_repo.get("j1")
    assert row is not None
    assert row.last_status == "ok"
    assert row.enabled == 1
    assert row.budget_tokens_used == 1_200
    assert audit.query(action="cron.budget_exceeded") == []


@pytest.mark.asyncio
async def test_run_zero_tokens_does_not_touch_budget(env) -> None:
    cron_repo, audit, _db, session_key = env
    cron_repo.update("j1", token_budget_24h=1)

    job = _job(
        cron_repo=cron_repo,
        audit=audit,
        session_key=session_key,
        delivery=_delivery_returning(0),
    )
    await asyncio.wait_for(job.run(), 5)

    row = cron_repo.get("j1")
    assert row is not None
    assert row.last_status == "ok"
    assert row.budget_tokens_used == 0
    assert row.enabled == 1
