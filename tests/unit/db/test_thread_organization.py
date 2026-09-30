"""Thread organization (folder + tags) repo behavior."""

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
def db_and_threads(tmp_path: Path) -> tuple[SqlitePool, ThreadRepo]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="Agent 1")
    return db, ThreadRepo(db)


def _insert(threads: ThreadRepo, thread_id: str, **kwargs: object) -> None:
    threads.insert(
        thread_id=thread_id,
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        session_key=ThreadRegistry.dashboard_key(agent_id="a1", user_id=1),
        **kwargs,
    )


def test_insert_with_folder_and_tags(db_and_threads: tuple[SqlitePool, ThreadRepo]):
    _db, threads = db_and_threads
    _insert(threads, "thr_1", folder="工作", tags=["重要", "项目"])
    row = threads.get("thr_1")
    assert row is not None
    assert row.folder == "工作"
    assert row.tags == ("重要", "项目")


def test_insert_defaults_legacy_compatible(db_and_threads: tuple[SqlitePool, ThreadRepo]):
    _db, threads = db_and_threads
    _insert(threads, "thr_legacy")
    row = threads.get("thr_legacy")
    assert row is not None
    assert row.folder is None
    assert row.tags == ()


def test_set_folder_and_clear(db_and_threads: tuple[SqlitePool, ThreadRepo]):
    _db, threads = db_and_threads
    _insert(threads, "thr_1")
    threads.set_folder("thr_1", "学习")
    assert threads.get("thr_1").folder == "学习"  # type: ignore[union-attr]
    threads.set_folder("thr_1", None)
    assert threads.get("thr_1").folder is None  # type: ignore[union-attr]
    threads.set_folder("thr_1", "   ")
    assert threads.get("thr_1").folder is None  # type: ignore[union-attr]


def test_set_tags_replace_and_clear(db_and_threads: tuple[SqlitePool, ThreadRepo]):
    _db, threads = db_and_threads
    _insert(threads, "thr_1", tags=["a"])
    threads.set_tags("thr_1", ["b", "c", "b", " ", "c"])
    assert threads.get("thr_1").tags == ("b", "c")  # type: ignore[union-attr]
    threads.set_tags("thr_1", [])
    assert threads.get("thr_1").tags == ()  # type: ignore[union-attr]


def test_list_folders_distinct_and_non_empty(db_and_threads: tuple[SqlitePool, ThreadRepo]):
    db, threads = db_and_threads
    _insert(threads, "thr_1", folder="工作")
    _insert(threads, "thr_2", folder="工作")
    _insert(threads, "thr_3", folder="学习")
    _insert(threads, "thr_4")
    with db.transaction() as conn:
        conn.execute("UPDATE threads SET folder = '' WHERE thread_id = 'thr_4'")
    assert threads.list_folders(agent_id="a1", user_id=1) == ["学习", "工作"]


def test_list_folders_scoped_per_user(db_and_threads: tuple[SqlitePool, ThreadRepo]):
    db, threads = db_and_threads
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) "
            "VALUES ('u2', 'h', 'user', 1)"
        )
    _insert(threads, "thr_1", folder="工作")
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO threads(thread_id, agent_id, user_id, channel_type, session_key, folder, last_active, created_at) "
            "VALUES ('thr_other', 'a1', 2, 'dashboard', 'k', '私密', 1, 1)"
        )
    assert threads.list_folders(agent_id="a1", user_id=1) == ["工作"]
    assert threads.list_folders(agent_id="a1", user_id=2) == ["私密"]


def test_list_by_folder_filters(db_and_threads: tuple[SqlitePool, ThreadRepo]):
    _db, threads = db_and_threads
    _insert(threads, "thr_1", folder="工作", last_active=3)
    _insert(threads, "thr_2", folder="工作", last_active=1)
    _insert(threads, "thr_3", folder="学习", last_active=2)
    _insert(threads, "thr_4", last_active=4)
    rows = threads.list_by_folder(agent_id="a1", user_id=1, folder="工作")
    assert [r.thread_id for r in rows] == ["thr_1", "thr_2"]
    rows = threads.list_by_folder(agent_id="a1", user_id=1, folder=None)
    assert [r.thread_id for r in rows] == ["thr_4"]


def test_list_by_tag_filters_quoted_element(db_and_threads: tuple[SqlitePool, ThreadRepo]):
    _db, threads = db_and_threads
    _insert(threads, "thr_1", tags=["工作", "重要"])
    _insert(threads, "thr_2", tags=["工作日报"])
    _insert(threads, "thr_3", tags=["学习"])
    rows = threads.list_by_tag(agent_id="a1", user_id=1, tag="工作")
    assert [r.thread_id for r in rows] == ["thr_1"]
    rows = threads.list_by_tag(agent_id="a1", user_id=1, tag="重要")
    assert [r.thread_id for r in rows] == ["thr_1"]
    rows = threads.list_by_tag(agent_id="a1", user_id=1, tag="不存在")
    assert rows == []


def test_legacy_row_with_null_folder_and_empty_tags(
    db_and_threads: tuple[SqlitePool, ThreadRepo],
):
    """Rows written before v15 (folder=NULL, tags='[]') map cleanly."""
    db, threads = db_and_threads
    _insert(threads, "thr_old")
    with db.transaction() as conn:
        conn.execute("UPDATE threads SET folder = NULL, tags = '[]' WHERE thread_id = 'thr_old'")
    row = threads.get("thr_old")
    assert row is not None
    assert row.folder is None
    assert row.tags == ()


def test_corrupt_tags_json_falls_back_to_empty(db_and_threads: tuple[SqlitePool, ThreadRepo]):
    db, threads = db_and_threads
    _insert(threads, "thr_bad", tags=["a"])
    with db.transaction() as conn:
        conn.execute("UPDATE threads SET tags = 'not-json' WHERE thread_id = 'thr_bad'")
    row = threads.get("thr_bad")
    assert row is not None
    assert row.tags == ()
