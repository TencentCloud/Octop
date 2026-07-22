"""tests/unit/test_usage_thread_totals.py"""

from __future__ import annotations

from pathlib import Path

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
    assert totals["output_tokens"] == 7
    assert totals["total_tokens"] == 20
    assert totals["turns"] == 2
