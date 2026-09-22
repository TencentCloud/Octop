"""Folded v17 migration: databases already past v17 still gain hitl_pending_records.

The HITL pending DDL lives inside the ``017`` pair. A database that recorded
v17 or later before the fold skips that file, so ``run_migrations`` must create
the table through the idempotent ensure helper — both for databases sitting at
the current maximum (tail wiring) and for pre-fold v17 databases that replay
the later upstream files (version-gated wiring).
"""

from __future__ import annotations

from pathlib import Path

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool


def _schema_version(db: SqlitePool) -> int:
    with db.connect() as conn:
        return int(conn.execute("SELECT version FROM _schema_version").fetchone()[0])


def _assert_hitl_table(db: SqlitePool) -> None:
    with db.connect() as conn:
        columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(hitl_pending_records)").fetchall()
        }
        indexes = {
            str(row["name"])
            for row in conn.execute("PRAGMA index_list(hitl_pending_records)").fetchall()
        }
    assert {
        "pending_id",
        "thread_id",
        "session_key",
        "status",
        "ask_question_index",
        "ask_answers",
    }.issubset(columns)
    assert {
        "idx_hitl_pending_records_session",
        "idx_hitl_pending_records_thread",
    }.issubset(indexes)


def test_prefold_database_gains_hitl_table_without_dedicated_migration(
    tmp_path: Path,
) -> None:
    db = SqlitePool(tmp_path / "prefold.db")
    run_migrations(db)
    max_version = _schema_version(db)

    # A database already past the fold records v18+ without the table; the
    # ensure helper at the run_migrations tail must backfill it in place.
    with db.connect() as conn:
        conn.execute("DROP TABLE hitl_pending_records")
    assert _schema_version(db) == max_version

    run_migrations(db)
    _assert_hitl_table(db)
    assert _schema_version(db) == max_version

    # A pre-fold v17 database replays the later upstream files and gains the
    # table through the version-gated ensure helper, not a new migration.
    with db.connect() as conn:
        conn.execute("DROP TABLE hitl_pending_records")
        conn.execute("UPDATE _schema_version SET version = 17")

    run_migrations(db)
    _assert_hitl_table(db)
    assert _schema_version(db) == max_version
