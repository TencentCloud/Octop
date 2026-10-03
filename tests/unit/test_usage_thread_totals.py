"""tests/unit/test_usage_thread_totals.py"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.usage import UsageRepo
from octop.infra.db.repos.users import UserRepo


def test_thread_totals_aggregate(tmp_path: Path):
    db = SqlitePool(tmp_path / "u.db")
    run_migrations(db)
    uid = UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=uid, name="a")
    repo = UsageRepo(db)
    repo.record(
        agent_id="a1",
        user_id=uid,
        thread_id="thr_1",
        input_tokens=10,
        uncached_input_tokens=4,
        cache_read_tokens=6,
        output_tokens=5,
        model="m",
    )
    repo.record(
        agent_id="a1",
        user_id=uid,
        thread_id="thr_1",
        input_tokens=3,
        output_tokens=2,
        model="m",
    )
    totals = repo.thread_totals(agent_id="a1", thread_id="thr_1")
    assert totals["input_tokens"] == 13
    assert totals["uncached_input_tokens"] == 7
    assert totals["cache_read_tokens"] == 6
    assert totals["output_tokens"] == 7
    assert totals["total_tokens"] == 20
    assert totals["model_calls"] == 2
    assert totals["turns"] == 2


def test_migration_repair_preserves_fully_cached_input(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "cached.db")
    run_migrations(db)
    uid = UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=uid, name="a")
    repo = UsageRepo(db)
    repo.record(
        agent_id="a1",
        user_id=uid,
        thread_id="thr_1",
        input_tokens=10,
        uncached_input_tokens=0,
        cache_read_tokens=10,
        output_tokens=1,
    )

    run_migrations(db)

    totals = repo.thread_totals(agent_id="a1", thread_id="thr_1")
    assert totals["uncached_input_tokens"] == 0
    assert totals["cache_read_tokens"] == 10


def test_summary_by_day_buckets_use_the_window_timezone(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "tz.db")
    run_migrations(db)
    uid = UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=uid, name="a")
    repo = UsageRepo(db)
    # One Shanghai day straddles two UTC days: 02:00 CST is 18:00 UTC the day before.
    for hour, tokens in ((2, 10), (14, 5)):
        ts = int(datetime(2026, 9, 22, hour, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp())
        repo.record(
            agent_id="a1",
            user_id=uid,
            input_tokens=tokens,
            output_tokens=0,
            model="m",
            ts=ts,
        )

    shanghai = repo.summary(
        window="range:2026-09-21:2026-09-22", granularity="by_day", timezone="Asia/Shanghai"
    )
    assert [b["key"] for b in shanghai["buckets"]] == ["2026-09-22"]
    assert sum(int(b["input_tokens"]) for b in shanghai["buckets"]) == shanghai["input_tokens"]

    # Same rows, UTC buckets: the 02:00 Shanghai row still belongs to 09-21.
    utc = repo.summary(window="range:2026-09-21:2026-09-22", granularity="by_day", timezone="UTC")
    assert [b["key"] for b in utc["buckets"]] == ["2026-09-22", "2026-09-21"]
