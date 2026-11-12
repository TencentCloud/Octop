"""Probe a database DSN without replacing the process pool."""

from __future__ import annotations

from typing import Any

from octop.config import DatabaseConfig, OctopConfig
from octop.infra.db.factory import open_database, resolve_sqlite_db_path
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout


def control_plane_user_count(db_config: DatabaseConfig, paths: PathLayout) -> int:
    """Users already stored in the target control plane.

    Returns 0 when the SQLite file does not exist yet, or when the ``users``
    table has not been created. Does not run migrations and does not create a
    SQLite file.
    """
    cfg = OctopConfig(database=db_config, database_in_file=True)
    if db_config.is_sqlite and not resolve_sqlite_db_path(cfg, paths).exists():
        return 0
    try:
        pool = open_database(cfg, paths)
    except Exception as exc:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"database connection failed: {exc}",
        ) from exc
    try:
        with pool.connect() as conn:
            return _count_users(conn, db_config.driver)
    except Exception as exc:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"database probe failed: {exc}",
        ) from exc
    finally:
        pool.close()


def probe_database(db_config: DatabaseConfig, paths: PathLayout) -> int:
    """Validate connectivity and return the existing control-plane user count.

    For an existing SQLite file or any PostgreSQL target, opens a short-lived
    pool and runs ``SELECT 1``. For a not-yet-created SQLite path, only ensures
    the parent directory is creatable — avoids creating an empty ``.db`` as a
    side effect of "test connection" — and returns 0.
    """
    cfg = OctopConfig(database=db_config, database_in_file=True)

    if db_config.is_sqlite:
        path = resolve_sqlite_db_path(cfg, paths)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                f"database path not writable: {exc}",
            ) from exc
        if not path.exists():
            return 0

    try:
        pool = open_database(cfg, paths)
    except Exception as exc:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"database connection failed: {exc}",
        ) from exc
    try:
        with pool.connect() as conn:
            conn.execute("SELECT 1")
            return _count_users(conn, db_config.driver)
    except Exception as exc:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"database probe failed: {exc}",
        ) from exc
    finally:
        pool.close()


def _count_users(conn: Any, driver: str) -> int:
    if driver == "sqlite":
        found = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'"
        ).fetchone()
        if found is None:
            return 0
    else:
        found = conn.execute("SELECT to_regclass('public.users')").fetchone()
        if found is None or found[0] is None:
            return 0
    row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    return int(row[0]) if row is not None else 0
