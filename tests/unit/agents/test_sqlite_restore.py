"""Real SQLite rollback, backup ownership and failure injection."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from octop_memory import Memory

from octop.infra.agents.memory.sqlite_restore import backup_path, list_backups, restore_sqlite


def create_store(path: Path, namespace: str = "agent_a") -> None:
    memory = Memory(namespace, backend_config={"db_path": str(path)})
    memory.put(
        {"configurable": {"thread_id": "t", "checkpoint_ns": ""}}, empty_checkpoint(), {}, {}
    )
    memory._checkpointer.conn.close()
    memory.backend.close()


def snapshot(path: Path) -> Path:
    backup = path.with_name(path.name + ".before-slim." + "a" * 32 + ".bak")
    with closing(sqlite3.connect(path)) as src, closing(sqlite3.connect(backup)) as dest:
        src.backup(dest)
    return backup


def count(path: Path) -> int:
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute("SELECT count(*) FROM checkpoints").fetchone()[0]


def test_restore_keeps_safety_backup_and_can_undo(tmp_path):
    path = tmp_path / "memory.sqlite"
    other = tmp_path / "other.sqlite"
    create_store(path)
    create_store(other, "agent_b")
    original_other = other.read_bytes()
    old = snapshot(path)
    memory = Memory("agent_a", backend_config={"db_path": str(path)})
    memory.put(
        {"configurable": {"thread_id": "new", "checkpoint_ns": ""}}, empty_checkpoint(), {}, {}
    )
    memory._checkpointer.conn.close()
    memory.backend.close()
    assert count(path) == 2
    report = restore_sqlite(path, "agent_a", old.name, locale="en", progress=lambda _: None)
    assert count(path) == 1
    safety = Path(report["backup_path"])
    assert count(safety) == 2
    assert len(list_backups(path)) == 2
    restore_sqlite(path, "agent_a", safety.name, locale="en", progress=lambda _: None)
    assert count(path) == 2
    assert other.read_bytes() == original_other


def test_corrupt_and_foreign_backups_do_not_modify_current_store(tmp_path):
    path = tmp_path / "memory.sqlite"
    create_store(path)
    old = snapshot(path)
    original = path.read_bytes()
    old.write_bytes(b"not sqlite")
    with pytest.raises(sqlite3.DatabaseError):
        restore_sqlite(path, "agent_a", old.name, locale="en", progress=lambda _: None)
    assert path.read_bytes() == original
    old.unlink()
    create_store(old, "agent_b")
    with pytest.raises(ValueError, match="different expert"):
        restore_sqlite(path, "agent_a", old.name, locale="en", progress=lambda _: None)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.before-restore.*"))
    with pytest.raises(ValueError):
        backup_path(path, "../" + old.name, "en")


def test_restore_flushes_safety_backup_with_writable_handle(tmp_path, monkeypatch):
    from octop.infra.agents.memory import sqlite_restore

    path = tmp_path / "memory.sqlite"
    create_store(path)
    old = snapshot(path)
    real_fsync = os.fsync
    flushed = []

    def require_writable_fsync(fd):
        # A zero-byte write enforces Windows' writable-handle requirement on
        # POSIX too, without changing the SQLite backup's contents.
        os.write(fd, b"")
        real_fsync(fd)
        flushed.append(fd)

    monkeypatch.setattr(sqlite_restore.os, "fsync", require_writable_fsync)
    report = restore_sqlite(path, "agent_a", old.name, locale="en", progress=lambda _: None)
    assert len(flushed) == 1
    assert count(Path(report["backup_path"])) == 1
    assert count(path) == 1


def test_validation_failure_after_restore_rolls_back_current_state(tmp_path, monkeypatch):
    from octop.infra.agents.memory import sqlite_restore

    path = tmp_path / "memory.sqlite"
    create_store(path)
    old = snapshot(path)
    memory = Memory("agent_a", backend_config={"db_path": str(path)})
    memory.put(
        {"configurable": {"thread_id": "new", "checkpoint_ns": ""}}, empty_checkpoint(), {}, {}
    )
    memory._checkpointer.conn.close()
    memory.backend.close()
    real = sqlite_restore._validate
    calls = 0

    def fail_after_copy(*args):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise ValueError("injected validation error")
        return real(*args)

    monkeypatch.setattr(sqlite_restore, "_validate", fail_after_copy)
    with pytest.raises(ValueError, match="injected"):
        restore_sqlite(path, "agent_a", old.name, locale="en", progress=lambda _: None)
    assert count(path) == 2
    assert len(list_backups(path)) == 2


def test_safety_backup_failure_never_overwrites_target(tmp_path, monkeypatch):
    from octop.infra.agents.memory import sqlite_restore

    path = tmp_path / "memory.sqlite"
    create_store(path)
    old = snapshot(path)
    original = path.read_bytes()
    monkeypatch.setattr(
        sqlite_restore.os, "fsync", lambda _: (_ for _ in ()).throw(OSError("disk full"))
    )
    with pytest.raises(OSError, match="disk full"):
        restore_sqlite(path, "agent_a", old.name, locale="en", progress=lambda _: None)
    assert path.read_bytes() == original
    assert len(list_backups(path)) == 1


def test_delete_backup_permission_failure_keeps_file(tmp_path, monkeypatch):
    from octop.infra.agents.memory.sqlite_restore import delete_backup

    path = tmp_path / "memory.sqlite"
    backup = path.with_name(path.name + ".before-slim." + "a" * 32 + ".bak")
    backup.write_bytes(b"keep this backup")

    def denied(self, **kwargs):
        raise PermissionError("read only directory")

    monkeypatch.setattr(Path, "unlink", denied)
    with pytest.raises(ValueError, match="Failed to delete"):
        delete_backup(path, backup.name, "en")
    assert backup.read_bytes() == b"keep this backup"
