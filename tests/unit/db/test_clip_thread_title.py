"""Thread repo title clipping and legacy hard-cut repair."""

from __future__ import annotations

from pathlib import Path

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.threads import (
    clip_thread_title,
    repair_all_legacy_thread_titles,
    repair_legacy_thread_title,
)


def test_clip_thread_title_short() -> None:
    assert clip_thread_title("hello") == "hello"
    assert clip_thread_title("  a  \n b  ") == "a b"
    assert clip_thread_title("") == ""
    assert clip_thread_title("   ") == ""


def test_clip_thread_title_long_with_ellipsis() -> None:
    body = "搜索当前热点新闻（微博热搜、知乎热榜、36氪等），整理成简洁的摘要推送给用户。格式要求"
    assert len(body) > 40
    out = clip_thread_title(body)
    assert out.endswith("…")
    assert len(out) == 40


def test_clip_keeps_exact_max_without_forcing_ellipsis() -> None:
    exact = "a" * 40
    assert clip_thread_title(exact) == exact


def test_repair_legacy_thread_title_hard_cut() -> None:
    hard = "搜索当前热点新闻（微博热搜、知乎热榜、36氪等），整理成简洁的摘要推送给用户。格"
    assert len(hard) == 40
    assert not hard.endswith("…")
    fixed = repair_legacy_thread_title(hard)
    assert fixed is not None
    assert fixed.endswith("…")
    assert len(fixed) == 40
    assert fixed == hard[:39] + "…"


def test_repair_legacy_passthrough_short() -> None:
    assert repair_legacy_thread_title("short") == "short"
    assert repair_legacy_thread_title(None) is None


def test_migration_003_repairs_stored_hard_cuts(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    with pool.connect() as conn:
        conn.executescript(
            (
                Path(__file__).resolve().parents[3]
                / "src/octop/infra/db/migrations/001_initial.sql"
            ).read_text()
        )
        # Partial v2 columns so full migrate can finish.
        conn.execute("ALTER TABLE cron_jobs ADD COLUMN mcp_servers TEXT NOT NULL DEFAULT '[]'")
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, 0)",
            ("u", "h", "user"),
        )
        uid = conn.execute("SELECT id FROM users WHERE username = ?", ("u",)).fetchone()[0]
        conn.execute(
            "INSERT INTO agents(agent_id, user_id, name, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, 0)",
            ("a1", uid, "Agent"),
        )
        hard = "x" * 40
        conn.execute(
            "INSERT INTO threads(thread_id, agent_id, user_id, channel_type, "
            "session_key, title, last_active, created_at, pinned) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
            ("t1", "a1", uid, "web", "s1", hard, 1, 1),
        )
        conn.execute("UPDATE _schema_version SET version = 1")
    run_migrations(pool)
    with pool.connect() as conn:
        v = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
        title = conn.execute("SELECT title FROM threads WHERE thread_id = ?", ("t1",)).fetchone()[0]
    assert v == 4
    assert title == "x" * 39 + "…"
    # Idempotent repair
    assert repair_all_legacy_thread_titles(pool) == 0
