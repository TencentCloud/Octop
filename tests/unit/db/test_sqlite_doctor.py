"""Unit tests for offline SQLite doctor, recovery, and SQLite connection hardening."""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from click.testing import CliRunner

from octop.cli.main import cli
from octop.infra.db.pool import SQLITE_BUSY_TIMEOUT_MS, SqlitePool
from octop.infra.db.sqlite_doctor import (
    discover_sqlite_files,
    inspect_sqlite_file,
    recover_sqlite_file,
)
from octop.infra.knowledge.graph_store import SqliteKnowledgeGraphStore
from octop.infra.knowledge.index import KnowledgeIndex


def _create_sample_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        conn.execute("INSERT INTO items (id, name) VALUES (1, 'alpha'), (2, 'beta')")
        conn.commit()


def test_sqlite_pool_sets_busy_timeout_and_checkpoints_on_close(tmp_path: Path) -> None:
    db_path = tmp_path / "octop.db"
    pool = SqlitePool(db_path)
    with pool.connect() as conn:
        timeout = int(conn.execute("PRAGMA busy_timeout").fetchone()[0])
        assert timeout == SQLITE_BUSY_TIMEOUT_MS
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
    pool.close()
    wal = db_path.with_name(db_path.name + "-wal")
    assert not wal.exists() or wal.stat().st_size == 0


def test_knowledge_sqlite_stores_enable_wal_and_busy_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    index = KnowledgeIndex("kb_test")
    with closing(index._connect()) as conn:
        assert str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
        assert int(conn.execute("PRAGMA busy_timeout").fetchone()[0]) >= 30_000

    graph = SqliteKnowledgeGraphStore("kb_test")
    with closing(graph._connect()) as conn:
        assert str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
        assert int(conn.execute("PRAGMA busy_timeout").fetchone()[0]) >= 30_000


def test_discover_and_inspect_sqlite_files(tmp_path: Path) -> None:
    control = tmp_path / "octop.db"
    agent_mem = tmp_path / "agents" / "ag1" / ".octop" / "memory.sqlite"
    kb_idx = tmp_path / "knowledge" / "kb1" / "index.sqlite"
    ignored_bak = tmp_path / "octop.db.corrupt-20261125.bak"
    ignored_backup_dir = tmp_path / "backups" / "snap.db"

    _create_sample_db(control)
    _create_sample_db(agent_mem)
    kb_idx.parent.mkdir(parents=True, exist_ok=True)
    kb_idx.write_bytes(b"not a valid sqlite file")
    ignored_bak.write_bytes(b"backup")
    _create_sample_db(ignored_backup_dir)

    discovered = discover_sqlite_files(tmp_path)
    assert discovered[0] == control.resolve()
    assert set(discovered) == {control.resolve(), agent_mem.resolve(), kb_idx.resolve()}

    ok_report = inspect_sqlite_file(control)
    assert ok_report.ok is True
    assert ok_report.messages == ["ok"]

    bad_report = inspect_sqlite_file(kb_idx)
    assert bad_report.ok is False
    assert bad_report.error


def test_recover_sqlite_file_python_iterdump_fallback(tmp_path: Path) -> None:
    db_path = tmp_path / "octop.db"
    _create_sample_db(db_path)

    result = recover_sqlite_file(db_path, mode="recover", sqlite3_bin="")
    assert result.ok is True
    assert result.method == "python_iterdump"
    assert Path(result.backup_path).is_file()
    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute("SELECT id, name FROM items ORDER BY id").fetchall()
    assert rows == [(1, "alpha"), (2, "beta")]


@pytest.mark.skipif(shutil.which("sqlite3") is None, reason="sqlite3 CLI not installed")
def test_recover_sqlite_file_via_sqlite3_cli(tmp_path: Path) -> None:
    db_path = tmp_path / "octop.db"
    _create_sample_db(db_path)

    result = recover_sqlite_file(db_path, mode="recover")
    assert result.ok is True
    assert result.method == "sqlite3_recover"
    assert Path(result.backup_path).is_file()
    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute("SELECT id, name FROM items ORDER BY id").fetchall()
    assert rows == [(1, "alpha"), (2, "beta")]


def test_recover_sqlite_file_reset_archives_and_removes_target(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite"
    db_path.write_bytes(b"broken")
    wal = db_path.with_name(db_path.name + "-wal")
    wal.write_bytes(b"stale")

    result = recover_sqlite_file(db_path, mode="reset")
    assert result.ok is True
    assert result.method == "reset"
    assert not db_path.exists()
    assert not wal.exists()
    assert Path(result.backup_path).read_bytes() == b"broken"


def test_cli_doctor_db_and_fix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    healthy = tmp_path / "octop.db"
    corrupt = tmp_path / "agents" / "ag1" / ".octop" / "memory.sqlite"
    _create_sample_db(healthy)
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_bytes(b"totally corrupted database")

    runner = CliRunner()
    res = runner.invoke(cli, ["--json", "doctor", "db"])
    assert res.exit_code == 1, res.output
    payload = json.loads(res.output)
    assert payload["ok"] is False
    assert payload["checked"] == 2
    assert payload["corrupt"] == 1

    reset_res = runner.invoke(cli, ["--json", "doctor", "db", "--fix", "--reset", "--yes"])
    assert reset_res.exit_code == 0, reset_res.output
    rec_payload = json.loads(reset_res.output)
    assert len(rec_payload["recovered"]) == 1
    assert rec_payload["recovered"][0]["method"] == "reset"
    assert not corrupt.exists()

    after = runner.invoke(cli, ["--json", "doctor", "db"])
    assert after.exit_code == 0, after.output
    assert json.loads(after.output)["ok"] is True
