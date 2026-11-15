"""Apply and verify migration 026 (hitl_pending_records).

Usage (run from the repository root)::

    OCTOP_TEST_DSN="host=127.0.0.1 dbname=octop_test user=octop password=..." \\
        python scripts/verify_hitl_pg_schema.py

Requires psycopg[binary]>=3.2. Guards use IF NOT EXISTS so re-running is safe.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

SQL_PATH = (
    Path(__file__).resolve().parents[1]
    / "src/octop/infra/db/migrations/026_hitl_pending_store.pg.sql"
)


def main() -> int:
    dsn = os.environ.get("OCTOP_TEST_DSN")
    if not dsn:
        print("missing OCTOP_TEST_DSN", file=sys.stderr)
        return 1

    sql = SQL_PATH.read_text(encoding="utf-8")
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS _schema_version (version INTEGER)")
        conn.execute("INSERT INTO _schema_version (version) VALUES (25)")
        conn.execute(sql)
        columns = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = %s ORDER BY ordinal_position",
            ("hitl_pending_records",),
        ).fetchall()
        indexes = conn.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = %s ORDER BY indexname",
            ("hitl_pending_records",),
        ).fetchall()
        row = conn.execute("SELECT count(*) FROM hitl_pending_records").fetchone()

    print("=== Columns ===")
    for name, dtype in columns:
        print(f"  {name:30s} {dtype}")
    print("=== Indexes ===")
    for (name,) in indexes:
        print(f"  {name}")
    print(f"Row count: {row[0] if row else 0}")
    print("Verification complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
