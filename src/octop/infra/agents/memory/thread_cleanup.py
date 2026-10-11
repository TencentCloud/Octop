"""Delete LangGraph checkpoints without a live HarnessAgent.

Conversation text lives in the agent's memory store (SQLite file or
Postgres), not in Octop's ``threads`` table. Callers delete checkpoints
first and drop the thread row only after this succeeds, so a failure
leaves the conversation visible and retryable.

Deleting an agent must do the same for every thread, then remove that
agent's memory rows. Those tables are not foreign keys of ``agents``.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from octop.config import OctopConfig
from octop.infra.agents.memory.backend import open_memory_kwargs
from octop.infra.agents.workspace.dir import (
    agent_host_data_dirs,
    host_system_dir,
    workspace_dir_from_config_json,
)
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

# ~8MB at the default 4KB page size. Matches
# octop_memory.pipeline.lifecycle.vacuum.DELETE_INCREMENTAL_VACUUM_PAGES.
_DELETE_VACUUM_PAGES = 2000

# Full VACUUM rewrites the file and needs about one extra copy on disk.
_COMPACT_DISK_MARGIN_BYTES = 64 * 1024 * 1024
_compact_disk_warned: set[str] = set()

# Idle maintenance compacts a store once deleted rows leave at least this
# much free space. Smaller holes stay on the hourly incremental pass.
RECLAIM_MIN_FREELIST_BYTES = 8 * 1024 * 1024

# Shared memory tables that carry a ``namespace`` column. Kept in sync with
# octop_memory's postgres ``_TABLES``. ``meta`` is instance-wide and stays.
_NAMESPACE_TABLES = (
    "memory_nodes",
    "raw_events",
    "candidates",
    "atoms",
    "entities",
    "aliases",
    "entity_pages",
    "thread_active_entities",
    "journal",
    "episodes",
    "digests",
)
# Schemas that hold every agent's rows. Never DROP these; only DELETE
# the namespace. ``harness_memory`` is the pre-rename shared schema.
_SHARED_MEMORY_SCHEMAS = frozenset({"octop_memory", "harness_memory", "public"})
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class OrphanCheckpoint:
    agent_id: str
    thread_id: str
    nbytes: int


def workspace_for_agent_row(row: Any, *, paths: Any) -> Path:
    """On-disk workspace for an agent row. Does not create the directory."""
    return workspace_dir_from_config_json(
        getattr(row, "config_json", None),
        paths=paths,
        agent_id=str(row.agent_id),
        ensure=False,
    )


def delete_thread_from_agent_stores(
    *,
    agent_id: str,
    thread_id: str,
    cfg: dict[str, Any],
    octop_config: OctopConfig,
    workspace_dir: Path,
    paths: Any | None = None,
) -> None:
    """Delete one conversation's checkpoints from Postgres and every SQLite file.

    The configured backend is always cleaned. SQLite files that sit in the
    agent's other workspace directories are cleaned too, so a Postgres agent
    does not leave a leftover ``memory.sqlite``.
    """
    delete_stored_thread(
        agent_id=agent_id,
        thread_id=thread_id,
        cfg=cfg,
        octop_config=octop_config,
        workspace_dir=workspace_dir,
    )
    _ns, _backend, _backend_config, primary = _memory_location(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=octop_config,
        workspace_dir=workspace_dir,
    )
    primary_resolved = primary.resolve() if primary is not None and primary.is_file() else None
    for path in _sqlite_memory_files(
        cfg, agent_id=agent_id, paths=paths, workspace_dir=workspace_dir
    ):
        if primary_resolved is not None and path == primary_resolved:
            continue
        delete_stored_thread(
            agent_id=agent_id,
            thread_id=thread_id,
            cfg=_sqlite_file_cfg(cfg, path),
            octop_config=octop_config,
            workspace_dir=workspace_dir,
        )


def delete_agent_memory_and_checkpoints(
    *,
    agent_id: str,
    thread_ids: set[str],
    cfg: dict[str, Any],
    octop_config: OctopConfig,
    workspace_dir: Path,
    paths: Any | None = None,
) -> None:
    """Remove one agent's checkpoints and memory rows.

    Call this before deleting the ``agents`` row. A failure leaves that
    row in place so the delete can be retried. SQLite with no file yet
    is a no-op. Postgres deletes the namespace from every shared memory
    schema (``octop_memory`` and the older ``harness_memory``).
    """
    for thread_id in sorted(thread_ids):
        delete_thread_from_agent_stores(
            agent_id=agent_id,
            thread_id=thread_id,
            cfg=cfg,
            octop_config=octop_config,
            workspace_dir=workspace_dir,
            paths=paths,
        )
    _purge_agent_memory(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=octop_config,
        workspace_dir=workspace_dir,
    )
    for path in _sqlite_memory_files(
        cfg,
        agent_id=agent_id,
        paths=paths,
        workspace_dir=workspace_dir,
    ):
        _purge_sqlite_file(
            agent_id=agent_id,
            cfg=_sqlite_file_cfg(cfg, path),
            octop_config=octop_config,
            workspace_dir=workspace_dir,
        )


def delete_stored_thread(
    *,
    agent_id: str,
    thread_id: str,
    cfg: dict[str, Any],
    octop_config: OctopConfig,
    workspace_dir: Path,
) -> None:
    """Remove ``thread_id`` from the agent's checkpoint store.

    Returns normally when the store does not exist yet or the thread was
    never written. Raises ``CHECKPOINT_DELETE_FAILED`` when a store is
    present and the delete does not complete. A following SQLite reclaim
    is best-effort and never fails the delete.
    """
    ns, backend, backend_config, sqlite_path = _memory_location(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=octop_config,
        workspace_dir=workspace_dir,
    )
    if backend == "sqlite" and (sqlite_path is None or not sqlite_path.is_file()):
        return

    memory = _open_memory(ns, backend, backend_config)
    try:
        try:
            memory.delete_thread(thread_id)
        except Exception as exc:
            if _store_has_no_checkpoints(exc):
                return
            raise _delete_failed(thread_id, exc) from exc
        _reclaim_sqlite(memory, agent_id=agent_id, thread_id=thread_id)
    finally:
        close_memory(memory)


def reclaim_stored_thread(
    *,
    agent_id: str,
    thread_id: str,
    cfg: dict[str, Any],
    octop_config: OctopConfig,
    workspace_dir: Path,
) -> None:
    """Best-effort SQLite reclaim after a live harness already deleted the rows."""
    ns, backend, backend_config, sqlite_path = _memory_location(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=octop_config,
        workspace_dir=workspace_dir,
    )
    if backend != "sqlite" or sqlite_path is None or not sqlite_path.is_file():
        return
    memory = _open_memory(ns, backend, backend_config)
    try:
        _reclaim_sqlite(memory, agent_id=agent_id, thread_id=thread_id)
    finally:
        close_memory(memory)


def checkpoint_thread_bytes(
    *,
    agent_id: str,
    cfg: dict[str, Any],
    octop_config: OctopConfig,
    workspace_dir: Path,
) -> dict[str, int]:
    """``thread_id -> checkpoint payload bytes`` currently stored for the agent."""
    _ns, backend, backend_config, sqlite_path = _memory_location(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=octop_config,
        workspace_dir=workspace_dir,
    )
    if backend == "sqlite":
        if sqlite_path is None or not sqlite_path.is_file():
            return {}
        return _sqlite_thread_bytes(sqlite_path)
    memory = _open_memory(_ns, backend, backend_config)
    try:
        return _postgres_thread_bytes(memory)
    finally:
        close_memory(memory)


def gc_orphan_checkpoints(
    services: Any, *, agent_id: str | None, apply: bool
) -> list[OrphanCheckpoint]:
    """Checkpoints whose thread row is already gone.

    ``apply=False`` only reports them. ``apply=True`` deletes each one
    through :func:`delete_stored_thread`.
    """
    rows = services.agent_repo.list_all(include_disabled=True)
    if agent_id is not None:
        rows = [row for row in rows if row.agent_id == agent_id]
    found: list[OrphanCheckpoint] = []
    for row in rows:
        cfg = agent_config_from_row(row)
        workspace = workspace_for_agent_row(row, paths=services.paths)
        usage = checkpoint_thread_bytes(
            agent_id=row.agent_id,
            cfg=cfg,
            octop_config=services.config,
            workspace_dir=workspace,
        )
        known = services.thread_repo.list_ids_for_agent(row.agent_id)
        orphans = [
            OrphanCheckpoint(agent_id=row.agent_id, thread_id=tid, nbytes=nbytes)
            for tid, nbytes in usage.items()
            if tid not in known
        ]
        if apply:
            for orphan in orphans:
                delete_stored_thread(
                    agent_id=row.agent_id,
                    thread_id=orphan.thread_id,
                    cfg=cfg,
                    octop_config=services.config,
                    workspace_dir=workspace,
                )
        found.extend(orphans)
    return found


def close_memory(memory: Any) -> None:
    """Release the checkpointer connection and the memory backend."""
    cp = getattr(memory, "_checkpointer", None)
    conn = getattr(cp, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            logger.debug("checkpoint connection close failed", exc_info=True)
    pool = getattr(memory, "_checkpointer_pool", None)
    closer = getattr(pool, "close", None)
    if closer is not None:
        try:
            closer()
        except Exception:
            logger.debug("checkpoint pool close failed", exc_info=True)
    backend = getattr(memory, "_backend", None)
    backend_close = getattr(backend, "close", None)
    if backend_close is not None:
        try:
            backend_close()
        except Exception:
            logger.debug("memory backend close failed", exc_info=True)


def agent_config_from_row(row: Any) -> dict[str, Any]:
    raw = getattr(row, "config_json", None)
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _memory_location(
    *,
    agent_id: str,
    cfg: dict[str, Any],
    octop_config: OctopConfig,
    workspace_dir: Path,
) -> tuple[str, str, dict[str, Any] | None, Path | None]:
    ns, backend, backend_config = open_memory_kwargs(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=octop_config,
        workspace_dir=workspace_dir,
    )
    sqlite_path: Path | None = None
    if backend == "sqlite":
        raw = (backend_config or {}).get("db_path")
        if raw:
            sqlite_path = Path(str(raw))
        else:
            sqlite_path = host_system_dir(workspace_dir, cfg) / "memory.sqlite"
    return ns, backend, backend_config if isinstance(backend_config, dict) else None, sqlite_path


def _open_memory(ns: str, backend: str, backend_config: dict[str, Any] | None) -> Any:
    from octop_memory.core import Memory

    return Memory(namespace=ns, backend=backend, backend_config=backend_config)


def _sqlite_file_cfg(cfg: dict[str, Any], path: Path) -> dict[str, Any]:
    merged = dict(cfg)
    memory = dict(merged.get("memory") or {}) if isinstance(merged.get("memory"), dict) else {}
    memory["backend"] = {"type": "sqlite", "db_path": str(path)}
    merged["memory"] = memory
    return merged


def _sqlite_memory_files(
    cfg: dict[str, Any],
    *,
    agent_id: str,
    paths: Any | None,
    workspace_dir: Path,
) -> list[Path]:
    """SQLite memory files for this agent, including ones outside the active workspace."""
    candidates = [
        host_system_dir(workspace_dir, cfg) / "memory.sqlite",
        workspace_dir / "memory.sqlite",
        workspace_dir / ".octop" / "memory.sqlite",
    ]
    if paths is not None:
        for directory in agent_host_data_dirs(cfg, paths=paths, agent_id=agent_id):
            candidates.append(directory / "memory.sqlite")
            candidates.append(directory / ".octop" / "memory.sqlite")
    found: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        found.append(resolved)
    return found


def _purge_sqlite_file(
    *,
    agent_id: str,
    cfg: dict[str, Any],
    octop_config: OctopConfig,
    workspace_dir: Path,
) -> None:
    _purge_agent_memory(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=octop_config,
        workspace_dir=workspace_dir,
    )


def _purge_agent_memory(
    *,
    agent_id: str,
    cfg: dict[str, Any],
    octop_config: OctopConfig,
    workspace_dir: Path,
) -> None:
    ns, backend, backend_config, sqlite_path = _memory_location(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=octop_config,
        workspace_dir=workspace_dir,
    )
    if backend == "sqlite" and (sqlite_path is None or not sqlite_path.is_file()):
        return
    memory = _open_memory(ns, backend, backend_config)
    try:
        store = getattr(memory, "_backend", None)
        if backend == "postgres":
            _purge_postgres_namespace(store)
        else:
            _drop_sqlite_namespace(store)
    finally:
        close_memory(memory)


def _quote_ident(name: str) -> str:
    if _IDENT.fullmatch(name) is None:
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return f'"{name}"'


def _purge_postgres_namespace(store: Any) -> None:
    """Delete this namespace from every shared memory schema on the DSN."""
    import psycopg

    ns = str(getattr(store, "_ns", "") or "")
    dsn = str(getattr(store, "_dsn", "") or "")
    if _IDENT.fullmatch(ns) is None or not dsn:
        raise OctopError(
            ErrorCode.CHECKPOINT_DELETE_FAILED,
            "could not delete agent memory: backend namespace is missing",
        )
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.columns
            WHERE column_name = 'namespace'
              AND table_name = ANY(%s)
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            """,
            (list(_NAMESPACE_TABLES),),
        )
        for schema, table in cur.fetchall():
            schema_name, table_name = str(schema), str(table)
            if _IDENT.fullmatch(schema_name) is None or _IDENT.fullmatch(table_name) is None:
                continue
            cur.execute(
                f"DELETE FROM {_quote_ident(schema_name)}.{_quote_ident(table_name)} "
                "WHERE namespace = %s",
                (ns,),
            )
        for legacy in (ns, f"{ns[:56]}__old"):
            if legacy in _SHARED_MEMORY_SCHEMAS:
                continue
            cur.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                (legacy,),
            )
            if cur.fetchone() is not None:
                cur.execute(f"DROP SCHEMA {_quote_ident(legacy)} CASCADE")


def _drop_sqlite_namespace(store: Any) -> None:
    """Drop this namespace's tables in a SQLite file that other agents may share."""
    ns = str(getattr(store, "_ns", "") or "")
    if _IDENT.fullmatch(ns) is None:
        return
    prefix = f"{ns}_"
    conn = store._conn
    rows = conn.execute("SELECT type, name FROM sqlite_master").fetchall()
    named = [(str(row[0]), str(row[1])) for row in rows if str(row[1]).startswith(prefix)]
    for kind, name in named:
        if kind == "trigger":
            conn.execute(f"DROP TRIGGER IF EXISTS {_quote_ident(name)}")
    tables = [name for kind, name in named if kind in {"table", "view"} and "_fts_" not in name]
    for name in tables:
        if name.endswith("_fts"):
            conn.execute(f"DROP TABLE IF EXISTS {_quote_ident(name)}")
    for name in tables:
        if not name.endswith("_fts"):
            conn.execute(f"DROP TABLE IF EXISTS {_quote_ident(name)}")
    conn.commit()


def sqlite_freelist_bytes(path: Path) -> int:
    """Bytes sitting on SQLite's freelist. ``0`` when the file is missing."""
    if not path.is_file():
        return 0
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except (OSError, sqlite3.Error):
        return 0
    try:
        page_row = conn.execute("PRAGMA page_size").fetchone()
        free_row = conn.execute("PRAGMA freelist_count").fetchone()
    except sqlite3.Error:
        return 0
    finally:
        conn.close()
    page = int(page_row[0] or 0) if page_row else 0
    free = int(free_row[0] or 0) if free_row else 0
    return page * free


def agent_sqlite_freelist_bytes(
    *,
    agent_id: str,
    cfg: dict[str, Any],
    octop_config: OctopConfig,
    workspace_dir: Path,
    paths: Any | None = None,
) -> int:
    """Free-page bytes across this agent's SQLite memory files."""
    found = _sqlite_memory_files(cfg, agent_id=agent_id, paths=paths, workspace_dir=workspace_dir)
    _ns, _backend, _backend_config, primary = _memory_location(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=octop_config,
        workspace_dir=workspace_dir,
    )
    if primary is not None:
        found.append(primary)
    total = 0
    seen: set[Path] = set()
    for path in found:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        total += sqlite_freelist_bytes(resolved)
    return total


def _store_file_bytes(path: Path) -> int:
    total = 0
    for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        if candidate.is_file():
            total += candidate.stat().st_size
    return total


def _disk_allows_compact(path: Path) -> bool:
    """False when rewriting the file would need more free disk than remains."""
    try:
        free = shutil.disk_usage(path).free
        need = _store_file_bytes(path) + _COMPACT_DISK_MARGIN_BYTES
    except OSError:
        logger.warning("compact disk check failed path=%s", path, exc_info=True)
        return False
    if free < need:
        key = str(path)
        if key not in _compact_disk_warned:
            _compact_disk_warned.add(key)
            logger.warning("skip compact path=%s free=%s need=%s", path, free, need)
        return False
    _compact_disk_warned.discard(str(path))
    return True


def compact_live_sqlite(memory: Any) -> bool:
    """Rebuild one open SQLite memory store so deleted rows leave the file.

    Returns True when the store is not SQLite, or the rebuild finished.
    Returns False when disk is short or the rebuild failed, so the caller
    can retry after the expert is idle. Postgres is left to autovacuum:
    ``VACUUM FULL`` would lock checkpoint tables shared by every agent.
    """
    from octop_memory.storage.backends.sqlite import SqliteMemoryBackend

    backend = getattr(memory, "_backend", None)
    if not isinstance(backend, SqliteMemoryBackend):
        return True
    path = Path(backend._db_path)
    if not path.is_file():
        return True
    if not _disk_allows_compact(path):
        return False
    try:
        from octop_memory.pipeline.lifecycle.vacuum import compact_vacuum

        compact_vacuum(memory)
    except Exception:
        logger.warning("compact failed path=%s", path, exc_info=True)
        return False
    return True


def compact_agent_store_file(
    *,
    agent_id: str,
    cfg: dict[str, Any],
    octop_config: OctopConfig,
    workspace_dir: Path,
) -> bool:
    """Open this agent's store and compact it. The agent must not be loaded."""
    ns, backend, backend_config, sqlite_path = _memory_location(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=octop_config,
        workspace_dir=workspace_dir,
    )
    if backend != "sqlite":
        return True
    if sqlite_path is None or not sqlite_path.is_file():
        return True
    memory = _open_memory(ns, backend, backend_config)
    try:
        return compact_live_sqlite(memory)
    finally:
        close_memory(memory)


def _reclaim_sqlite(memory: Any, *, agent_id: str, thread_id: str) -> None:
    from octop_memory.pipeline.lifecycle.vacuum import nudge_vacuum
    from octop_memory.storage.backends.sqlite import SqliteMemoryBackend

    if not isinstance(getattr(memory, "_backend", None), SqliteMemoryBackend):
        return
    try:
        nudge_vacuum(memory, pages=_DELETE_VACUUM_PAGES)
    except Exception:
        logger.warning(
            "checkpoint reclaim failed agent=%s thread=%s",
            agent_id,
            thread_id,
            exc_info=True,
        )


def _sqlite_thread_bytes(path: Path) -> dict[str, int]:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA query_only=ON")
        names = {
            str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "checkpoints" not in names:
            return {}
        rows = conn.execute(
            "SELECT thread_id, COALESCE(SUM(LENGTH(checkpoint)), 0) "
            "FROM checkpoints GROUP BY thread_id"
        ).fetchall()
    except sqlite3.Error as exc:
        if _store_has_no_checkpoints(exc):
            return {}
        raise
    finally:
        conn.close()
    return {str(thread_id): int(nbytes or 0) for thread_id, nbytes in rows}


def _postgres_thread_bytes(memory: Any) -> dict[str, int]:
    memory._ensure_checkpointer()
    saver = memory._checkpointer
    cursor = getattr(saver, "_cursor", None)
    if cursor is None:
        return {}
    try:
        with cursor() as cur:
            cur.execute(
                "SELECT thread_id, COALESCE(SUM(pg_column_size(checkpoint)), 0) AS nbytes "
                "FROM checkpoints GROUP BY thread_id"
            )
            rows = cur.fetchall()
    except Exception as exc:
        if _store_has_no_checkpoints(exc):
            return {}
        raise
    out: dict[str, int] = {}
    for row in rows:
        if isinstance(row, dict):
            out[str(row["thread_id"])] = int(row["nbytes"] or 0)
        else:
            out[str(row[0])] = int(row[1] or 0)
    return out


def _store_has_no_checkpoints(exc: BaseException) -> bool:
    text = str(exc).lower()
    if "no such table" in text:
        return True
    return type(exc).__name__ == "UndefinedTable" or (
        "does not exist" in text and "checkpoint" in text
    )


def memory_namespace(agent_id: str) -> str:
    """Namespace stored for an agent, matching the memory backends."""
    return re.sub(r"[^a-z0-9_]", "_", f"agent_{agent_id}".lower())


def sweep_deleted_residuals(
    agent_manager: Any, *, remove_directories: bool = False
) -> dict[str, Any]:
    """Drop memory and checkpoints left behind by deleted agents or threads.

    Safe to call from memory slim. Live agents and their current threads are
    kept. Directories under ``agents/`` and ``workspaces/`` whose names match
    no agent are only removed when ``remove_directories`` is true; otherwise
    their paths are returned for a second confirmation. Postgres namespaces
    and checkpoint rows are removed only from databases this instance uses.
    """
    repos = getattr(agent_manager, "_repos", None)
    paths = getattr(agent_manager, "_paths", None)
    config = getattr(agent_manager, "_config", None)
    if repos is None or paths is None or config is None:
        return {"namespaces": 0, "threads": 0, "directories": 0, "directory_paths": []}
    rows = repos.agent_repo.list_all(include_disabled=True)
    live_ids = {str(row.agent_id) for row in rows}
    live_namespaces = {memory_namespace(agent_id) for agent_id in live_ids}
    live_threads: set[str] = set()
    for agent_id in live_ids:
        live_threads |= repos.thread_repo.list_ids_for_agent(agent_id)

    threads_removed = 0
    namespaces_removed = 0
    seen_dsn: set[str] = set()
    if config.database.is_postgresql:
        dsn = config.database.postgresql_conninfo()
        seen_dsn.add(dsn)
        threads_removed += _delete_postgres_orphan_checkpoints(dsn, live_threads)
        namespaces_removed += _delete_postgres_orphan_namespaces(dsn, live_namespaces)
    for row in rows:
        cfg = agent_config_from_row(row)
        workspace = workspace_for_agent_row(row, paths=paths)
        _ns, backend, backend_config, sqlite_path = _memory_location(
            agent_id=row.agent_id,
            cfg=cfg,
            octop_config=config,
            workspace_dir=workspace,
        )
        if backend == "postgres":
            dsn = str((backend_config or {}).get("dsn") or "")
            if dsn and dsn not in seen_dsn:
                seen_dsn.add(dsn)
                threads_removed += _delete_postgres_orphan_checkpoints(dsn, live_threads)
                namespaces_removed += _delete_postgres_orphan_namespaces(dsn, live_namespaces)
            continue
        agent_threads = repos.thread_repo.list_ids_for_agent(row.agent_id)
        files = _sqlite_memory_files(
            cfg, agent_id=row.agent_id, paths=paths, workspace_dir=workspace
        )
        if sqlite_path is not None and sqlite_path.is_file():
            files.append(sqlite_path.resolve())
        for path in dict.fromkeys(files):
            threads_removed += _delete_sqlite_orphan_checkpoints(path, agent_threads)
    directory_paths = [str(path) for path in list_deleted_agent_dirs(paths, live_ids)]
    directories_removed = _remove_deleted_agent_dirs(paths, live_ids) if remove_directories else 0
    return {
        "namespaces": namespaces_removed,
        "threads": threads_removed,
        "directories": directories_removed,
        "directory_paths": directory_paths,
    }


def _delete_sqlite_orphan_checkpoints(path: Path, live_threads: set[str]) -> int:
    if not path.is_file():
        return 0
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        names = {
            str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "checkpoints" not in names:
            return 0
        if live_threads:
            slots = ",".join("?" * len(live_threads))
            orphan_rows = conn.execute(
                f"SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id NOT IN ({slots})",
                tuple(live_threads),
            ).fetchall()
        else:
            orphan_rows = conn.execute("SELECT DISTINCT thread_id FROM checkpoints").fetchall()
        orphan_ids = [str(row[0]) for row in orphan_rows]
        if not orphan_ids:
            return 0
        slots = ",".join("?" * len(orphan_ids))
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            if table in names:
                conn.execute(f"DELETE FROM {table} WHERE thread_id IN ({slots})", tuple(orphan_ids))
        conn.commit()
        return len(orphan_ids)
    finally:
        conn.close()


def _delete_postgres_orphan_checkpoints(dsn: str, live_threads: set[str]) -> int:
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.checkpoints')")
        found = cur.fetchone()
        if found is None or found[0] is None:
            return 0
        if live_threads:
            cur.execute(
                "SELECT DISTINCT thread_id FROM checkpoints WHERE NOT (thread_id = ANY(%s))",
                (list(live_threads),),
            )
        else:
            cur.execute("SELECT DISTINCT thread_id FROM checkpoints")
        orphan_ids = [str(row[0]) for row in cur.fetchall()]
        if not orphan_ids:
            return 0
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
            found = cur.fetchone()
            if found is None or found[0] is None:
                continue
            cur.execute(
                f"DELETE FROM public.{table} WHERE thread_id = ANY(%s)",
                (orphan_ids,),
            )
        return len(orphan_ids)


def _delete_postgres_orphan_namespaces(dsn: str, live_namespaces: set[str]) -> int:
    import psycopg

    removed = 0
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.columns
            WHERE column_name = 'namespace'
              AND table_name = ANY(%s)
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            """,
            (list(_NAMESPACE_TABLES),),
        )
        targets = [(str(schema), str(table)) for schema, table in cur.fetchall()]
        namespaces: set[str] = set()
        for schema, table in targets:
            if _IDENT.fullmatch(schema) is None or _IDENT.fullmatch(table) is None:
                continue
            cur.execute(
                f"SELECT DISTINCT namespace FROM {_quote_ident(schema)}.{_quote_ident(table)} "
                "WHERE namespace LIKE 'agent_%'"
            )
            namespaces.update(str(row[0]) for row in cur.fetchall() if row[0])
        stale = sorted(
            ns for ns in namespaces if ns not in live_namespaces and _IDENT.fullmatch(ns)
        )
        if not stale:
            return 0
        for schema, table in targets:
            if _IDENT.fullmatch(schema) is None or _IDENT.fullmatch(table) is None:
                continue
            cur.execute(
                f"DELETE FROM {_quote_ident(schema)}.{_quote_ident(table)} WHERE namespace = ANY(%s)",
                (stale,),
            )
        for namespace in stale:
            for legacy in (namespace, f"{namespace[:56]}__old"):
                if legacy in _SHARED_MEMORY_SCHEMAS or _IDENT.fullmatch(legacy) is None:
                    continue
                cur.execute(
                    "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                    (legacy,),
                )
                if cur.fetchone() is not None:
                    cur.execute(f"DROP SCHEMA {_quote_ident(legacy)} CASCADE")
        removed = len(stale)
    return removed


def list_deleted_agent_dirs(paths: Any, live_ids: set[str]) -> list[Path]:
    """Directories under agents/ and workspaces/ whose names match no agent."""
    found: list[Path] = []
    for parent in (paths.root / "agents", paths.root / "workspaces"):
        if not parent.is_dir():
            continue
        for child in sorted(parent.iterdir(), key=lambda item: item.name):
            if not child.is_dir() or child.name in live_ids or child.name.startswith("."):
                continue
            found.append(child)
    return found


def _remove_deleted_agent_dirs(paths: Any, live_ids: set[str]) -> int:
    import shutil

    removed = 0
    for child in list_deleted_agent_dirs(paths, live_ids):
        try:
            shutil.rmtree(child)
        except OSError:
            logger.exception("failed to remove leftover agent directory %s", child)
            continue
        removed += 1
    return removed


def _delete_failed(thread_id: str, exc: BaseException) -> OctopError:
    logger.warning("checkpoint delete failed thread=%s", thread_id, exc_info=exc)
    return OctopError(
        ErrorCode.CHECKPOINT_DELETE_FAILED,
        f"could not delete conversation data for thread {thread_id!r}",
    )
