"""Probe a database DSN without replacing the process pool."""

from __future__ import annotations

from octop.config import DatabaseConfig, OctopConfig
from octop.infra.db.factory import open_database, resolve_sqlite_db_path
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout


def probe_database(db_config: DatabaseConfig, paths: PathLayout) -> None:
    """Validate connectivity (or path writability for new SQLite files).

    For an existing SQLite file or any PostgreSQL target, opens a short-lived
    pool and runs ``SELECT 1``. For a not-yet-created SQLite path, only ensures
    the parent directory is creatable — avoids creating an empty ``.db`` as a
    side effect of "test connection".
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
            return

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
    except Exception as exc:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"database probe failed: {exc}",
        ) from exc
    finally:
        pool.close()
