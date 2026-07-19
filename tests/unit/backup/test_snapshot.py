"""Unit tests for SQLite snapshot helpers."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from octop.infra.backup.snapshot import snapshot_sqlite_file


@pytest.mark.skipif(os.name == "nt", reason="Windows disallows '?' in path names")
def test_snapshot_sqlite_file_with_special_chars_in_path(tmp_path: Path) -> None:
    """Paths containing URI metacharacters must not alter connect options."""
    tricky_dir = tmp_path / "dir?mode=memory"
    tricky_dir.mkdir()
    source = tricky_dir / "data.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE t (v TEXT)")
        conn.execute("INSERT INTO t VALUES ('ok')")

    dest = tmp_path / "backup.db"
    snapshot_sqlite_file(source, dest)

    with sqlite3.connect(dest) as conn:
        row = conn.execute("SELECT v FROM t").fetchone()
    assert row is not None
    assert row[0] == "ok"
