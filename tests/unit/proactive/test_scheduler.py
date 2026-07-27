"""Unit tests for ProactiveCareScheduler.

Coverage:
- compute_next_trigger: random scheduling inside active hours
- compute_next_trigger: defer to the next active window when outside active hours
- is_in_active_hours: active-window checks
- ProactiveCareScheduler: enabled=false should not trigger
- ProactiveCareScheduler: dynamic reschedule updates
- ProactiveCareConfigRepo: get/upsert/list_enabled
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.proactive_care_config import ProactiveCareConfig, ProactiveCareConfigRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.proactive.scheduler import (
    ProactiveCareScheduler,
    compute_next_trigger,
    is_in_active_hours,
)
from octop.infra.utils.ulid import new_ulid

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "test.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def agent_id(db: SqlitePool) -> str:
    uid = UserRepo(db).create(username="alice", password_hash="h", role="admin")
    aid = new_ulid()
    AgentRepo(db).create(agent_id=aid, user_id=uid, name="bot")
    return aid


@pytest.fixture
def config_repo(db: SqlitePool) -> ProactiveCareConfigRepo:
    return ProactiveCareConfigRepo(db)


# ---------------------------------------------------------------------------
# compute_next_trigger tests
# ---------------------------------------------------------------------------


def test_compute_next_trigger_in_active_hours():
    """Should return the candidate time directly when it is inside active hours."""
    # Current time is UTC 10:00, active window is 09:00-22:00, interval is 1h.
    now = datetime(2026, 7, 1, 10, 0, 0, tzinfo=UTC)
    # Fix the random seed so the interval stays inside active hours.
    import random

    random.seed(42)
    # Force the interval to 60 minutes, which remains inside active hours.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("random.randint", lambda a, b: 60)  # Fixed 60 minutes.
        result = compute_next_trigger(
            now=now,
            active_hours_start="09:00",
            active_hours_end="22:00",
            min_interval_hours=1,
            max_interval_hours=2,
        )
    # The result should remain inside active hours.
    result_t = result.time().replace(second=0, microsecond=0)
    assert time(9, 0) <= result_t < time(22, 0)


def test_compute_next_trigger_outside_active_hours_deferred():
    """Should defer to the next active window when the candidate is outside active hours."""
    # Current time is UTC 14:00, active window is 09:00-22:00, interval is 10h.
    now = datetime(2026, 7, 1, 14, 0, 0, tzinfo=UTC)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("random.randint", lambda a, b: 600)  # Fixed 600 minutes = 10h.
        result = compute_next_trigger(
            now=now,
            active_hours_start="09:00",
            active_hours_end="22:00",
            min_interval_hours=8,
            max_interval_hours=24,
        )
    # The result should be inside active hours on the next day.
    result_t = result.time().replace(second=0, microsecond=0)
    assert time(9, 0) <= result_t < time(22, 0)
    # The result should be on the next day.
    assert result.date() > now.date()


def test_compute_next_trigger_already_past_active_hours():
    """Should defer to tomorrow when now and candidate time are past active hours."""
    now = datetime(2026, 7, 1, 23, 0, 0, tzinfo=UTC)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("random.randint", lambda a, b: 60)  # 1h later = next-day 00:00.
        result = compute_next_trigger(
            now=now,
            active_hours_start="09:00",
            active_hours_end="22:00",
            min_interval_hours=1,
            max_interval_hours=2,
        )
    result_t = result.time().replace(second=0, microsecond=0)
    assert time(9, 0) <= result_t < time(22, 0)


def test_compute_next_trigger_returns_future():
    """compute_next_trigger should always return a time after now."""
    now = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
    for _ in range(20):
        result = compute_next_trigger(
            now=now,
            active_hours_start="09:00",
            active_hours_end="22:00",
            min_interval_hours=8,
            max_interval_hours=24,
        )
        assert result > now


# ---------------------------------------------------------------------------
# is_in_active_hours tests
# ---------------------------------------------------------------------------


def test_is_in_active_hours_true():
    """Should return True inside active hours."""
    now = datetime(2026, 7, 1, 15, 30, 0, tzinfo=UTC)
    assert is_in_active_hours(now, active_hours_start="09:00", active_hours_end="22:00") is True


def test_is_in_active_hours_false_before():
    """Should return False before active hours."""
    now = datetime(2026, 7, 1, 8, 0, 0, tzinfo=UTC)
    assert is_in_active_hours(now, active_hours_start="09:00", active_hours_end="22:00") is False


def test_is_in_active_hours_false_after():
    """Should return False after active hours."""
    now = datetime(2026, 7, 1, 22, 30, 0, tzinfo=UTC)
    assert is_in_active_hours(now, active_hours_start="09:00", active_hours_end="22:00") is False


def test_is_in_active_hours_boundary_start():
    """Should return True exactly at the active-window start."""
    now = datetime(2026, 7, 1, 9, 0, 0, tzinfo=UTC)
    assert is_in_active_hours(now, active_hours_start="09:00", active_hours_end="22:00") is True


def test_is_in_active_hours_boundary_end():
    """Should return False exactly at the active-window end."""
    now = datetime(2026, 7, 1, 22, 0, 0, tzinfo=UTC)
    assert is_in_active_hours(now, active_hours_start="09:00", active_hours_end="22:00") is False


# ---------------------------------------------------------------------------
# ProactiveCareConfigRepo tests
# ---------------------------------------------------------------------------


def test_config_repo_get_default(agent_id: str, config_repo: ProactiveCareConfigRepo):
    """Should return defaults when no config exists."""
    cfg = config_repo.get(agent_id)
    assert cfg.agent_id == agent_id
    assert cfg.enabled is True
    assert cfg.active_hours_start == "09:00"
    assert cfg.active_hours_end == "22:00"
    assert cfg.min_interval_hours == 5
    assert cfg.max_interval_hours == 24


def test_config_repo_upsert_and_get(agent_id: str, config_repo: ProactiveCareConfigRepo):
    """Should read the saved config after upsert."""
    cfg = ProactiveCareConfig(
        agent_id=agent_id,
        enabled=True,
        active_hours_start="10:00",
        active_hours_end="20:00",
        min_interval_hours=4,
        max_interval_hours=12,
    )
    config_repo.upsert(cfg)
    got = config_repo.get(agent_id)
    assert got.enabled is True
    assert got.active_hours_start == "10:00"
    assert got.active_hours_end == "20:00"
    assert got.min_interval_hours == 4
    assert got.max_interval_hours == 12


def test_config_repo_upsert_update(agent_id: str, config_repo: ProactiveCareConfigRepo):
    """Repeated upsert should update the existing config."""
    cfg1 = ProactiveCareConfig(agent_id=agent_id, enabled=True)
    config_repo.upsert(cfg1)
    cfg2 = ProactiveCareConfig(agent_id=agent_id, enabled=False, min_interval_hours=12)
    config_repo.upsert(cfg2)
    got = config_repo.get(agent_id)
    assert got.enabled is False
    assert got.min_interval_hours == 12


def test_config_repo_list_enabled(db: SqlitePool, config_repo: ProactiveCareConfigRepo):
    """list_enabled should return only enabled configs."""
    uid = UserRepo(db).create(username="bob", password_hash="h", role="admin")
    aid1 = new_ulid()
    aid2 = new_ulid()
    AgentRepo(db).create(agent_id=aid1, user_id=uid, name="bot1")
    AgentRepo(db).create(agent_id=aid2, user_id=uid, name="bot2")

    config_repo.upsert(ProactiveCareConfig(agent_id=aid1, enabled=True))
    config_repo.upsert(ProactiveCareConfig(agent_id=aid2, enabled=False))

    enabled = config_repo.list_enabled()
    enabled_ids = {c.agent_id for c in enabled}
    assert aid1 in enabled_ids
    assert aid2 not in enabled_ids


# ---------------------------------------------------------------------------
# ProactiveCareScheduler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_cancel_stops_task(
    agent_id: str,
    config_repo: ProactiveCareConfigRepo,
    db: SqlitePool,
):
    """cancel should stop the scheduled task."""
    from octop.infra.db.repos.sessions import SessionRepo

    care_service = AsyncMock()
    session_repo = SessionRepo(db)

    # Enable the config.
    config_repo.upsert(ProactiveCareConfig(agent_id=agent_id, enabled=True))

    scheduler = ProactiveCareScheduler(
        care_service=care_service,
        config_repo=config_repo,
        session_repo=session_repo,
    )

    # Schedule manually.
    scheduler._schedule(agent_id)
    assert agent_id in scheduler._tasks

    # Cancel.
    scheduler.cancel(agent_id)
    # Wait for the task to be cancelled.
    await asyncio.sleep(0.01)
    assert agent_id not in scheduler._tasks


@pytest.mark.asyncio
async def test_scheduler_reschedule_disabled(
    agent_id: str,
    config_repo: ProactiveCareConfigRepo,
    db: SqlitePool,
):
    """reschedule should cancel the task when enabled=false."""
    from octop.infra.db.repos.sessions import SessionRepo

    care_service = AsyncMock()
    session_repo = SessionRepo(db)

    # Enable first.
    config_repo.upsert(ProactiveCareConfig(agent_id=agent_id, enabled=True))
    scheduler = ProactiveCareScheduler(
        care_service=care_service,
        config_repo=config_repo,
        session_repo=session_repo,
    )
    scheduler._schedule(agent_id)
    assert agent_id in scheduler._tasks

    # Disable, then reschedule.
    config_repo.upsert(ProactiveCareConfig(agent_id=agent_id, enabled=False))
    scheduler.reschedule(agent_id)
    await asyncio.sleep(0.01)
    assert agent_id not in scheduler._tasks


@pytest.mark.asyncio
async def test_scheduler_start_all_no_enabled(
    config_repo: ProactiveCareConfigRepo,
    db: SqlitePool,
):
    """start_all should not create tasks when no agent is enabled."""
    from octop.infra.db.repos.sessions import SessionRepo

    care_service = AsyncMock()
    session_repo = SessionRepo(db)
    scheduler = ProactiveCareScheduler(
        care_service=care_service,
        config_repo=config_repo,
        session_repo=session_repo,
    )
    await scheduler.start_all()
    assert len(scheduler._tasks) == 0
