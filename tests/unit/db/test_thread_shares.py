"""Read-only conversation share links."""

from __future__ import annotations

from pathlib import Path

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.thread_shares import ThreadShareRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo


def _repo(tmp_path: Path) -> tuple[ThreadShareRepo, str, int]:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    user_id = UserRepo(pool).create(username="ada", password_hash="x", role="user")
    AgentRepo(pool).create(agent_id="agt", user_id=user_id, name="Helper")
    ThreadRepo(pool).insert(
        thread_id="thr",
        agent_id="agt",
        user_id=user_id,
        channel_type="dashboard",
        session_key="sk",
        title="Weekly",
    )
    return ThreadShareRepo(pool), "thr", user_id


def test_ensure_reuses_the_live_link(tmp_path: Path) -> None:
    repo, thread_id, user_id = _repo(tmp_path)
    first = repo.ensure(thread_id=thread_id, agent_id="agt", created_by=user_id)
    second = repo.ensure(thread_id=thread_id, agent_id="agt", created_by=user_id)
    assert first.share_id == second.share_id
    assert repo.get_active_by_token(first.share_id) is not None


def test_rotate_and_revoke_invalidate_the_old_token(tmp_path: Path) -> None:
    repo, thread_id, user_id = _repo(tmp_path)
    first = repo.ensure(thread_id=thread_id, agent_id="agt", created_by=user_id)
    rotated = repo.rotate(thread_id=thread_id, agent_id="agt", created_by=user_id)
    assert rotated.share_id != first.share_id
    assert repo.get_active_by_token(first.share_id) is None
    assert repo.get_active_by_token(rotated.share_id) is not None
    repo.revoke(thread_id)
    assert repo.get_active_by_thread(thread_id) is None
    assert repo.get_active_by_token(rotated.share_id) is None


def test_deleting_the_thread_drops_the_link(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    user_id = UserRepo(pool).create(username="ada", password_hash="x", role="user")
    AgentRepo(pool).create(agent_id="agt", user_id=user_id, name="Helper")
    threads = ThreadRepo(pool)
    threads.insert(
        thread_id="thr",
        agent_id="agt",
        user_id=user_id,
        channel_type="dashboard",
        session_key="sk",
    )
    repo = ThreadShareRepo(pool)
    share = repo.ensure(thread_id="thr", agent_id="agt", created_by=user_id)
    threads.delete("thr")
    assert repo.get_active_by_token(share.share_id) is None
