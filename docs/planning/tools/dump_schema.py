# -*- coding: utf-8 -*-
"""Dump a table's columns from a freshly migrated SQLite database."""
from __future__ import annotations

import pathlib
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

from octop.infra.db.migrate import run_migrations  # noqa: E402
from octop.infra.db.pool import SqlitePool  # noqa: E402

table = sys.argv[1] if len(sys.argv) > 1 else "threads"
d = pathlib.Path(tempfile.mkdtemp())
pool = SqlitePool(d / "o.db")
run_migrations(pool)
with pool.connect() as conn:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
print(f"{table}:")
for r in rows:
    print(f"  {r['name']:<26} {r['type']:<10} notnull={r['notnull']} default={r['dflt_value']}")
