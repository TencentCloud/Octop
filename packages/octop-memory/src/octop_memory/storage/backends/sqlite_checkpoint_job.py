"""SQLite offline maintenance job: connections, backup and storage operations."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import Any


def maintain_checkpoints(
    db_path: Path,
    *,
    apply: bool = False,
    offline: bool = False,
    backup: Path | None = None,
    expand: bool = False,
    batch_size: int = 100,
    completed_threads: tuple[str, ...] = (),
    keep_last: int | None = None,
    protected_ids: tuple[str, ...] = (),
    vacuum: bool = False,
) -> dict[str, Any]:
    """Inspect or migrate an existing SQLite file, with an exclusive new backup.

    ``offline`` attests all users of this DB have stopped; it is not a service
    stop command or a distributed lock. Committed batches make interrupted
    migrations restartable. Backups cover the complete file, including memory
    tables; restoring one therefore requires coordinating all subsequent data.
    """
    if apply and (not offline or backup is None):
        raise ValueError("Applying checkpoint maintenance requires --offline and a new --backup path")
    if vacuum and not apply:
        raise ValueError("--vacuum requires --apply")
    if (keep_last is not None) != bool(completed_threads):
        raise ValueError("Use --keep-last and --completed-thread together")
    if keep_last is not None and keep_last < 1:
        raise ValueError("keep_last must be >= 1")
    if expand and completed_threads:
        raise ValueError("Format rollback cannot be combined with history pruning")
    if not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    path = db_path.expanduser().resolve(strict=True)
    before = _file_sizes(path)
    from octop_memory.storage.backends.sqlite_checkpoint import CompactSqliteSaver
    from octop_memory.storage.backends.sqlite_checkpoint_maintenance import (
        collect_unused_blobs,
        migrate_checkpoints,
        prune_completed_threads,
    )

    with closing(sqlite3.connect(path.as_uri() + ("?mode=rw" if apply else "?mode=ro"), uri=True)) as conn:
        if not apply:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("SQLite quick_check failed")
        saver = CompactSqliteSaver(conn, compact=not expand)
        # Preflight the entire source before the first schema or payload edit.
        for kind, payload in conn.execute("SELECT type, checkpoint FROM checkpoints"):
            saver.codec.loads_typed((kind, payload))
        known_ids = {row[0] for row in conn.execute("SELECT checkpoint_id FROM checkpoints")}
        if set(protected_ids) - known_ids:
            raise ValueError("A protected checkpoint ID is not present in this database")
        if apply:
            assert backup is not None
            backup = backup.expanduser().absolute()
            # Never overwrite a backup or loosen access to its private payloads.
            fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            backup_ok = False
            try:
                with closing(sqlite3.connect(str(backup))) as dest:
                    conn.backup(dest)
                    if dest.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise ValueError("Backup quick_check failed")
                backup_ok = True
            finally:
                if not backup_ok:
                    backup.unlink()
            saver.setup()
        stats = migrate_checkpoints(saver, apply=apply, expand=expand, batch_size=batch_size)
        if keep_last is not None:
            prune_completed_threads(
                saver,
                stats,
                completed_threads=tuple(dict.fromkeys(completed_threads)),
                keep_last=keep_last,
                protected_ids=protected_ids,
                apply=apply,
            )
        if apply:
            stats.blobs_deleted = collect_unused_blobs(saver)
            if vacuum:
                conn.execute("VACUUM")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        pages = {
            key: conn.execute(f"PRAGMA {key}").fetchone()[0] for key in ("page_count", "page_size", "freelist_count")
        }
    return {
        "stats": asdict(stats),
        "before": before,
        "after": _file_sizes(path),
        "pages": pages,
        "backup_bytes": backup.stat().st_size if apply and backup else 0,
        "note": "Payload projection excludes blob/index overhead; file sizes and backup bytes are reported separately.",
    }


def _file_sizes(path: Path) -> dict[str, int]:
    wal = Path(str(path) + "-wal")
    return {"file_bytes": path.stat().st_size, "wal_bytes": wal.stat().st_size if wal.exists() else 0}
