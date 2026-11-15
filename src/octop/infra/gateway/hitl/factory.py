"""Pick the HITL pending store implementation that matches the control plane."""

from __future__ import annotations

import logging

from octop.infra.gateway.hitl.store import HitlPendingStore

_log = logging.getLogger(__name__)


def build_pending_store() -> HitlPendingStore:
    """Return the pending store for the configured control plane.

    PostgreSQL installs with migration 026 applied get the durable
    ``HitlPendingPostgresStore``. SQLite installs, unconfigured hosts, and every
    failure path (missing driver, unreachable server, absent table) fall back to
    the in-memory store so chat keeps working instead of failing at boot.
    """
    from octop.config import database_env_configured, load_config
    from octop.infra.utils.paths import PathLayout

    try:
        config_path = PathLayout.from_env().config
        if not config_path.exists() and not database_env_configured():
            return HitlPendingStore()
        config = load_config(config_path)
    except Exception:
        _log.warning(
            "hitl pending store: config unavailable, using in-memory store",
            exc_info=True,
        )
        return HitlPendingStore()

    if not config.database.is_postgresql:
        return HitlPendingStore()

    try:
        import psycopg

        from octop.infra.gateway.hitl.pg_store import HitlPendingPostgresStore

        conninfo = config.database.postgresql_conninfo()
        # Probe connectivity and the 026 table so a half-configured host
        # degrades to the in-memory store instead of failing on the first pause.
        with psycopg.connect(conninfo, connect_timeout=5) as conn:
            conn.execute("SELECT 1 FROM hitl_pending_records LIMIT 1")
        return HitlPendingPostgresStore(conninfo)
    except Exception:
        _log.warning(
            "hitl pending store: postgres unavailable, using in-memory store",
            exc_info=True,
        )
        return HitlPendingStore()
