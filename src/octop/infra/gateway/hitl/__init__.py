"""Channel HITL — pending store, formatting, and resume orchestration."""

from __future__ import annotations

from typing import Any

from octop.infra.agents.security.hitl_session import (
    HitlSessionPolicy,
    HitlSessionPolicyStore,
    parse_hitl_session_policy,
)
from octop.infra.gateway.hitl.coordinator import (
    HitlChannelCoordinator,
    HitlSlashOutcome,
    HitlStreamContext,
)
from octop.infra.gateway.hitl.store import HitlPendingRecord, HitlPendingStore

__all__ = [
    "HitlChannelCoordinator",
    "HitlPendingPostgresStore",
    "HitlPendingRecord",
    "HitlPendingStore",
    "HitlSessionPolicy",
    "HitlSessionPolicyStore",
    "HitlSlashOutcome",
    "HitlStreamContext",
    "parse_hitl_session_policy",
]


def __getattr__(name: str) -> Any:
    """Resolve the PostgreSQL store lazily on first access.

    ``pg_store`` imports ``psycopg`` and ``psycopg_pool`` at module scope. SQLite
    installations do not ship those drivers, and importing this package (which
    every ``hitl.store`` consumer triggers) must not fail there, so the name is
    resolved on demand instead of at import time.
    """
    if name == "HitlPendingPostgresStore":
        from octop.infra.gateway.hitl.pg_store import HitlPendingPostgresStore

        return HitlPendingPostgresStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
