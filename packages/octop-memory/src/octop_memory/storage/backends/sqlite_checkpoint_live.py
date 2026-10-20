"""Host-coordinated live field migration; no pruning or blob deletion.

Compatible WAL readers may retain their snapshots. Concurrent writers are
serialized by SQLite, with each migration batch reading after BEGIN IMMEDIATE.
The host must use reference-aware readers and pause new graph invocations.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import Any

from octop_memory.storage.backends.sqlite_checkpoint import CompactSqliteSaver
from octop_memory.storage.backends.sqlite_checkpoint_job import _file_sizes
from octop_memory.storage.backends.sqlite_checkpoint_maintenance import MigrationStats, migrate_checkpoints


def slim_live_checkpoints(
    db_path: Path,
    *,
    backup: Path,
    progress: Callable[[dict[str, Any]], None] | None = None,
    batch_size: int = 100,
) -> dict[str, Any]:
    """Back up and deduplicate an existing SQLite store while its host is paused.

    This does not close live connections or delete history/content. A failure
    preserves committed batches as a readable mixed-format store. Never restore
    the backup automatically: other writers may have committed since it was made.
    """
    if not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    path = db_path.expanduser().resolve(strict=True)
    backup = backup.expanduser().absolute()
    before = _file_sizes(path)

    def emit(phase: str, **values: Any) -> None:
        if progress is not None:
            progress({"phase": phase, **values})

    with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)) as conn:
        if conn.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            raise ValueError("Live checkpoint maintenance requires WAL mode")
        emit("backing_up")
        fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        backup_ok = False
        try:
            with closing(sqlite3.connect(backup)) as dest:
                conn.backup(dest)
                result = dest.execute("PRAGMA quick_check").fetchone()[0]
                if result != "ok":
                    raise ValueError(f"Backup quick_check failed: {result}")
                codec = CompactSqliteSaver(dest).codec
                for kind, payload in dest.execute("SELECT type, checkpoint FROM checkpoints"):
                    codec.loads_typed((kind, payload))
            backup_ok = True
        finally:
            if not backup_ok:
                backup.unlink()

        saver = CompactSqliteSaver(conn)
        saver.setup()
        high_water, count = conn.execute("SELECT coalesce(max(rowid),0),count(*) FROM checkpoints").fetchone()
        emit("deduplicating", scanned=0, total=count)

        def update(stats: MigrationStats) -> None:
            emit("deduplicating", scanned=stats.scanned, total=count)

        stats = migrate_checkpoints(saver, apply=True, batch_size=batch_size, through_rowid=high_water, progress=update)
        # Do not run offline mark/sweep: live readers/caches remain valid.
        emit("compacting", scanned=stats.scanned, total=count)
        conn.execute("VACUUM")
        busy, _, _ = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if busy:
            raise ValueError("Deduplication completed, but a live reader still holds WAL; retry reclamation later")
    return {
        "stats": asdict(stats),
        "before": before,
        "after": _file_sizes(path),
        "backup_path": str(backup),
        "backup_bytes": backup.stat().st_size,
    }
