"""Migration 022: ``project_comments.concluded_by_type`` / ``concluded_by_id``.

The conclusion mark has an actor for as long as the mark lives (PLAN.md §2.1c), so
022 adds the two nullable columns that record it. Additive DDL only: no rebuild, no
``migrate.py`` helper — the same shape as 021.
"""

from __future__ import annotations

from pathlib import Path

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool


def _columns(pool: SqlitePool, table: str) -> set[str]:
    with pool.connect() as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def _version(pool: SqlitePool) -> int:
    with pool.connect() as conn:
        return int(conn.execute("SELECT version FROM _schema_version").fetchone()["version"])


def test_head_is_22(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    assert _version(pool) == 25


def test_both_columns_exist_and_are_nullable(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    columns = _columns(pool, "project_comments")
    assert {"concluded_by_type", "concluded_by_id"} <= columns
    with pool.connect() as conn:
        info = {str(r["name"]): r for r in conn.execute("PRAGMA table_info(project_comments)")}
    for name in ("concluded_by_type", "concluded_by_id"):
        assert info[name]["notnull"] == 0, f"{name} must stay nullable"
        assert (info[name]["type"] or "").upper() == "TEXT", name


def test_rerunning_migrations_is_idempotent(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    before = _columns(pool, "project_comments")
    run_migrations(pool)  # second pass must be a no-op, not a duplicate-column error
    assert _version(pool) == 25
    assert _columns(pool, "project_comments") == before


def test_the_pair_is_self_contained_on_both_dialects() -> None:
    """SQLite adds two plain columns; the PG twin guards each with IF NOT EXISTS."""
    sqlite_sql = Path(
        "src/octop/infra/db/migrations/022_project_comment_concluded_by.sql"
    ).read_text(encoding="utf-8")
    pg_sql = Path(
        "src/octop/infra/db/migrations/022_project_comment_concluded_by.pg.sql"
    ).read_text(encoding="utf-8")
    for column in ("concluded_by_type", "concluded_by_id"):
        assert f"ALTER TABLE project_comments ADD COLUMN {column} TEXT;" in sqlite_sql
        assert f"ALTER TABLE project_comments ADD COLUMN IF NOT EXISTS {column} TEXT;" in pg_sql, (
            f"{column} must be guarded on the PG side"
        )
    assert "UPDATE _schema_version SET version = 22;" in sqlite_sql
    assert "UPDATE _schema_version SET version = 22;" in pg_sql
    # Every PG statement ends with `;\n` so the statement splitter sees them whole.
    for statement in pg_sql.split(";\n"):
        body = "\n".join(
            line for line in statement.splitlines() if not line.strip().startswith("--")
        ).strip()
        if body:
            assert body.upper().startswith(("ALTER TABLE", "UPDATE")), body


def test_no_migrate_helper_was_added() -> None:
    migrate = Path("src/octop/infra/db/migrate.py").read_text(encoding="utf-8")
    assert "concluded_by" not in migrate, "022 must slot into the generic SQL path"
