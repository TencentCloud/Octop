"""``ThreadRepo.list_by_user`` — the cross-agent sidebar scan (PLAN.md §3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.threads import ThreadRegistry


@pytest.fixture
def env(tmp_path: Path) -> tuple[ThreadRepo, SqlitePool, int, int]:
    """Two users, two agents per user, one repository."""
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    users = UserRepo(db)
    owner = users.create(username="owner", password_hash="h", role="user")
    other = users.create(username="other", password_hash="h", role="user")
    agents = AgentRepo(db)
    agents.create(agent_id="a1", user_id=owner, name="Agent 1")
    agents.create(agent_id="a2", user_id=owner, name="Agent 2")
    agents.create(agent_id="a3", user_id=other, name="Agent 3")
    return ThreadRepo(db), db, owner, other


def _insert(
    repo: ThreadRepo, thread_id: str, *, agent_id: str, user_id: int, **extra: object
) -> None:
    repo.insert(
        thread_id=thread_id,
        agent_id=agent_id,
        user_id=user_id,
        channel_type="dashboard",
        session_key=ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=user_id),
        **extra,  # type: ignore[arg-type]
    )


def test_list_by_user_spans_agents_and_excludes_other_users(
    env: tuple[ThreadRepo, SqlitePool, int, int],
) -> None:
    repo, _, owner, other = env
    _insert(repo, "thr_a1", agent_id="a1", user_id=owner, last_active=10)
    _insert(repo, "thr_a2", agent_id="a2", user_id=owner, last_active=20)
    _insert(repo, "thr_a3", agent_id="a3", user_id=other, last_active=999)

    rows = repo.list_by_user(user_id=owner, limit=50)

    assert [r.thread_id for r in rows] == ["thr_a2", "thr_a1"]
    assert {r.agent_id for r in rows} == {"a1", "a2"}
    assert all(r.user_id == owner for r in rows)


def test_list_by_user_is_empty_for_a_user_without_threads(
    env: tuple[ThreadRepo, SqlitePool, int, int],
) -> None:
    repo, _, _, other = env
    assert repo.list_by_user(user_id=other, limit=50) == []


def test_list_by_user_pins_first_then_newest_activity(
    env: tuple[ThreadRepo, SqlitePool, int, int],
) -> None:
    repo, _, owner, _ = env
    _insert(repo, "thr_old", agent_id="a1", user_id=owner, last_active=100)
    _insert(repo, "thr_new", agent_id="a1", user_id=owner, last_active=200)
    _insert(repo, "thr_pinned_stale", agent_id="a2", user_id=owner, last_active=1)
    repo.set_pinned("thr_pinned_stale", True)

    rows = repo.list_by_user(user_id=owner, limit=50)

    assert [r.thread_id for r in rows] == ["thr_pinned_stale", "thr_new", "thr_old"]
    assert rows[0].pinned is True


def test_list_by_user_falls_back_to_created_at_for_untouched_threads(
    env: tuple[ThreadRepo, SqlitePool, int, int],
) -> None:
    """``last_active = 0`` means no turns yet, so a brand-new thread still sorts
    by ``created_at`` instead of sinking below every previously active chat."""
    repo, db, owner, _ = env
    _insert(repo, "thr_untouched_new", agent_id="a1", user_id=owner, last_active=0)
    _insert(repo, "thr_untouched_old", agent_id="a2", user_id=owner, last_active=0)
    _insert(repo, "thr_active", agent_id="a1", user_id=owner, last_active=50)
    with db.transaction() as conn:
        conn.execute("UPDATE threads SET created_at = 300 WHERE thread_id = 'thr_untouched_new'")
        conn.execute("UPDATE threads SET created_at = 100 WHERE thread_id = 'thr_untouched_old'")

    rows = repo.list_by_user(user_id=owner, limit=50)

    assert [r.thread_id for r in rows] == [
        "thr_untouched_new",  # created_at 300, no turns
        "thr_untouched_old",  # created_at 100, no turns
        "thr_active",  # last_active 50
    ]


def test_list_by_user_breaks_ties_on_thread_id_descending(
    env: tuple[ThreadRepo, SqlitePool, int, int],
) -> None:
    repo, _, owner, _ = env
    for thread_id in ("thr_b", "thr_a", "thr_c"):
        _insert(repo, thread_id, agent_id="a1", user_id=owner, last_active=0)

    rows = repo.list_by_user(user_id=owner, limit=50)

    assert [r.thread_id for r in rows] == ["thr_c", "thr_b", "thr_a"]


def test_list_by_user_honours_the_limit(env: tuple[ThreadRepo, SqlitePool, int, int]) -> None:
    repo, _, owner, _ = env
    for i in range(5):
        _insert(repo, f"thr_{i}", agent_id="a1", user_id=owner, last_active=i + 1)

    assert [r.thread_id for r in repo.list_by_user(user_id=owner, limit=2)] == ["thr_4", "thr_3"]


def test_list_by_user_default_limit_is_50(env: tuple[ThreadRepo, SqlitePool, int, int]) -> None:
    repo, _, owner, _ = env
    for i in range(55):
        _insert(repo, f"thr_{i:02d}", agent_id="a1", user_id=owner, last_active=i + 1)

    assert len(repo.list_by_user(user_id=owner)) == 50
