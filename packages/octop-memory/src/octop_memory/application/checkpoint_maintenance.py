"""Backend dispatch for explicit checkpoint maintenance; never boots an agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def maintain_checkpoints(db_path: Path, *, backend: str = "sqlite", **options: Any) -> dict[str, Any]:
    """Inspect/migrate SQLite checkpoints; reject unsupported backends explicitly.

    Options and offline guarantees are defined by the SQLite maintenance job.
    Import it lazily so the core/CLI remain usable without LangGraph extras.
    """
    if backend != "sqlite":
        raise ValueError("Checkpoint field migration is SQLite-only; PostgreSQL keeps its existing saver")
    from octop_memory.storage.backends.sqlite_checkpoint_job import maintain_checkpoints as run

    return run(db_path, **options)


def slim_live_checkpoints(db_path: Path, *, backend: str = "sqlite", **options: Any) -> dict[str, Any]:
    """Host-only live maintenance; the host supplies compatible readers and a pause gate."""
    if backend != "sqlite":
        raise ValueError("Live checkpoint maintenance is SQLite-only")
    from octop_memory.storage.backends.sqlite_checkpoint_live import slim_live_checkpoints as run

    return run(db_path, **options)
