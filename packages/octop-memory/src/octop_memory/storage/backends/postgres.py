"""PostgreSQL-based memory backend with tsvector full-text search."""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from octop_memory.domain.datetime import as_utc
from octop_memory.storage.backends import _UNSET, _Unset
from octop_memory.storage.backends.postgres_pool import acquire_pool
from octop_memory.types import (
    ActiveEntity,
    Alias,
    AtomCard,
    Candidate,
    CandidateStatus,
    DigestPeriod,
    DigestRecord,
    Entity,
    EntityPage,
    EntityType,
    Episode,
    ImportanceLevel,
    JournalAction,
    JournalEntry,
    MemoryNode,
    RawEvent,
    RawEventType,
)

logger = logging.getLogger(__name__)

# All namespaces share one fixed set of tables inside this schema.
SHARED_SCHEMA = "octop_memory"

# Version of the shared-table layout, stamped into ``meta``. Bump when the
# DDL below changes shape and add a corresponding migration.
SCHEMA_VERSION = "1"

# Arbitrary constant identifying "octop-memory DDL" for pg_advisory_xact_lock,
# so concurrent Memory instances (multiple agents / processes booting at once)
# serialize their CREATE-IF-NOT-EXISTS work instead of racing in pg_catalog.
_DDL_LOCK_KEY = 0x68_6D_65_6D  # "hmem"
_DDL_LOCK_TIMEOUT = "5s"

# Tables with a generated tsvector column, and that column's name. Their FTS
# indexes are namespace-scoped by ``_scope_fts_indexes_by_namespace``.
_FTS_INDEXES: tuple[tuple[str, str], ...] = (
    ("memory_nodes", "content_tsv"),
    ("raw_events", "content_tsv"),
    ("candidates", "fts_tsv"),
    ("atoms", "fts_tsv"),
    ("episodes", "fts_tsv"),
)

# Tables owned by this backend, in parent-before-child order (memory_nodes has
# a self-reference only, so ordering is irrelevant today, but keep the list as
# the single source of truth for purge/migration loops).
_TABLES = (
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


def _rowcount(value: Any) -> int:
    """Normalize DB-API rowcount values for strict typing."""
    return int(value) if value is not None else 0


class PostgresMemoryBackend:
    """Memory backend using PostgreSQL + tsvector/GIN full-text search.

    Multi-agent isolation via a ``namespace`` column on a fixed set of shared
    tables (schema ``octop_memory``) — NOT one schema per agent. Every
    primary key and secondary index is namespace-first, so per-agent lookups
    stay index-driven regardless of how many agents share the database.
    FTS GIN indexes are single-column (tsvector); the planner combines them
    with the namespace-first btree indexes via bitmap-AND.

    Legacy layouts (one schema per namespace, from earlier builds) are
    migrated automatically on first open: rows are copied into the shared
    tables and the old schema is renamed to ``{ns}__old`` as a backup.

    Default DSN: ``postgresql://localhost/octop_memory``.
    """

    def __init__(
        self,
        namespace: str,
        dsn: str = "postgresql://localhost/octop_memory",
        **kwargs: Any,
    ) -> None:
        self._ns = re.sub(r"[^a-z0-9_]", "_", namespace.lower())
        self._dsn = dsn
        self._connect_kwargs = dict(kwargs)
        self._conn: Any = None  # only held while an operation/transaction owns it
        self._in_transaction = False
        self._closed = False
        self._conn_lock = threading.RLock()
        self._booting = True
        self._pool = acquire_pool(dsn, purpose="business", connect_kwargs=kwargs)
        try:
            with self._connection():
                self._init_schema()
                self._migrate_legacy_schema()
        except BaseException:
            self.close()
            raise
        finally:
            self._booting = False

    def close(self) -> None:
        """Wait for this backend's operation, then release its pool reference."""
        with self._conn_lock:
            if not self._closed:
                self._closed = True
                self._pool.close()

    @contextmanager
    def _connection(self) -> Generator[Any, None, None]:
        """Borrow once per operation; nested calls retain the transaction."""
        with self._conn_lock:
            if self._closed:
                raise psycopg.OperationalError("the memory backend is closed")
            if self._conn is not None:
                yield self._conn
                return
            with self._pool.connection() as conn:
                self._conn = conn
                try:
                    yield conn
                finally:
                    self._conn = None

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Hold one connection and lock for the complete atomic transaction."""
        with self._connection() as conn:
            if self._in_transaction:
                yield
                return
            with conn.transaction():
                self._in_transaction = True
                try:
                    yield
                finally:
                    self._in_transaction = False

    @contextmanager
    def _cursor(self) -> Generator[Any, None, None]:
        """Finish standalone transactions before returning the connection."""
        with self._connection() as conn:
            if self._in_transaction or self._booting:
                with conn.cursor() as cur:
                    yield cur
            else:
                with conn.transaction(), conn.cursor() as cur:
                    yield cur

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        with self._cursor() as cur:
            # A stale reader must fail this bootstrap promptly instead of
            # leaving ``octop run`` apparently hung before uvicorn binds.
            cur.execute(f"SET LOCAL lock_timeout = '{_DDL_LOCK_TIMEOUT}'")
            # Serialize concurrent boot-time DDL across agents/processes.
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (_DDL_LOCK_KEY,))
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SHARED_SCHEMA}")
            cur.execute(f"SET search_path TO {SHARED_SCHEMA}, public")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            cur.execute(
                """INSERT INTO meta (key, value) VALUES ('schema_version', %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                (SCHEMA_VERSION,),
            )

            # NOTE: ``parent_id`` deliberately has NO ``ON DELETE CASCADE``.
            # Cascade deletion is implemented at the service layer
            # (``Memory.delete``) so that SQLite and Postgres behave
            # identically — SQLite has no FK cascade. If the reference
            # were CASCADE here, accidental raw DELETEs would silently
            # wipe entire subtrees on Postgres but raise on SQLite.
            # DEFERRABLE so legacy-schema migration can bulk-copy rows in
            # arbitrary order within one transaction.
            cur.execute("""
                CREATE TABLE IF NOT EXISTS memory_nodes (
                    namespace TEXT NOT NULL,
                    id TEXT NOT NULL,
                    parent_id TEXT,
                    level TEXT NOT NULL CHECK (level IN ('root', 'branch', 'leaf')),
                    atom_id TEXT,
                    content TEXT NOT NULL,
                    topic TEXT,
                    conversation_id TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    content_tsv TSVECTOR GENERATED ALWAYS AS (
                        to_tsvector('simple', content) || to_tsvector('simple', COALESCE(topic, ''))
                    ) STORED,
                    PRIMARY KEY (namespace, id),
                    UNIQUE (namespace, atom_id),
                    FOREIGN KEY (namespace, parent_id)
                        REFERENCES memory_nodes (namespace, id)
                        DEFERRABLE INITIALLY IMMEDIATE
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS memory_nodes_parent ON memory_nodes(namespace, parent_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS memory_nodes_level ON memory_nodes(namespace, level)")
            cur.execute("CREATE INDEX IF NOT EXISTS memory_nodes_fts ON memory_nodes USING GIN(content_tsv)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS raw_events (
                    namespace TEXT NOT NULL,
                    id TEXT NOT NULL,
                    host TEXT NOT NULL,
                    session_id TEXT,
                    thread_id TEXT,
                    "user" TEXT,
                    timestamp TIMESTAMPTZ NOT NULL,
                    event_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    content_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
                    PRIMARY KEY (namespace, id)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS raw_events_time ON raw_events(namespace, timestamp)")
            cur.execute("CREATE INDEX IF NOT EXISTS raw_events_session ON raw_events(namespace, session_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS raw_events_thread ON raw_events(namespace, thread_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS raw_events_host ON raw_events(namespace, host)")
            cur.execute("CREATE INDEX IF NOT EXISTS raw_events_type ON raw_events(namespace, event_type)")
            cur.execute("CREATE INDEX IF NOT EXISTS raw_events_fts ON raw_events USING GIN(content_tsv)")

            # ----------------------------------------------------------
            # M2: L1 Candidates
            # ----------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS candidates (
                    namespace TEXT NOT NULL,
                    id TEXT NOT NULL,
                    raw_event_ids JSONB NOT NULL,
                    candidate_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    assertion TEXT NOT NULL,
                    verbatim_quote TEXT NOT NULL,
                    quote_event_id TEXT NOT NULL,
                    subject_name TEXT NOT NULL,
                    subject_entity_type TEXT NOT NULL,
                    target_entity_id TEXT,
                    confidence TEXT NOT NULL,
                    importance TEXT NOT NULL,
                    recommended_action TEXT NOT NULL,
                    promotion_reason TEXT NOT NULL,
                    extractor_version TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    decided_at TIMESTAMPTZ,
                    decided_by TEXT,
                    session_id TEXT,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    fts_tsv TSVECTOR GENERATED ALWAYS AS (
                        to_tsvector('simple', title || ' ' || assertion || ' ' || verbatim_quote)
                    ) STORED,
                    PRIMARY KEY (namespace, id)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS candidates_status ON candidates(namespace, status)")
            cur.execute("CREATE INDEX IF NOT EXISTS candidates_session ON candidates(namespace, session_id)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS candidates_target_entity ON candidates(namespace, target_entity_id)"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS candidates_created_at ON candidates(namespace, created_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS candidates_fts ON candidates USING GIN(fts_tsv)")

            # ----------------------------------------------------------
            # M2: L2 Atoms
            # ----------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS atoms (
                    namespace TEXT NOT NULL,
                    id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    raw_event_ids JSONB NOT NULL,
                    assertion TEXT NOT NULL,
                    verbatim_quote TEXT NOT NULL,
                    quote_event_id TEXT NOT NULL,
                    search_terms JSONB NOT NULL,
                    occurred_at TIMESTAMPTZ NOT NULL,
                    confidence TEXT NOT NULL,
                    importance TEXT NOT NULL,
                    superseded_by TEXT,
                    deprecated_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL,
                    fts_tsv TSVECTOR GENERATED ALWAYS AS (
                        to_tsvector(
                            'simple',
                            assertion || ' ' || verbatim_quote || ' ' ||
                            COALESCE(jsonb_path_query_array(search_terms, '$[*]')::text, '')
                        )
                    ) STORED,
                    PRIMARY KEY (namespace, id)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS atoms_entity ON atoms(namespace, entity_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS atoms_importance ON atoms(namespace, importance)")
            cur.execute("CREATE INDEX IF NOT EXISTS atoms_created_at ON atoms(namespace, created_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS atoms_occurred_at ON atoms(namespace, occurred_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS atoms_superseded ON atoms(namespace, superseded_by)")
            cur.execute("CREATE INDEX IF NOT EXISTS atoms_fts ON atoms USING GIN(fts_tsv)")

            # ----------------------------------------------------------
            # M2: L3 Entities (minimal — no summary; D28)
            # ----------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    namespace TEXT NOT NULL,
                    id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    canonical_name TEXT NOT NULL,
                    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
                    atom_count INTEGER NOT NULL DEFAULT 0,
                    last_promoted_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (namespace, id)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS entities_type ON entities(namespace, entity_type)")
            cur.execute("CREATE INDEX IF NOT EXISTS entities_name ON entities(namespace, LOWER(canonical_name))")

            # ----------------------------------------------------------
            # M2: Aliases (string-normalized lookup)
            # ----------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS aliases (
                    namespace TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (namespace, alias, entity_id)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS aliases_alias ON aliases(namespace, alias)")
            cur.execute("CREATE INDEX IF NOT EXISTS aliases_entity ON aliases(namespace, entity_id)")

            # ----------------------------------------------------------
            # M3: L3 Entity Pages (long-form summary; D32-D37)
            # ----------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS entity_pages (
                    namespace TEXT NOT NULL,
                    id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    summary_markdown TEXT NOT NULL DEFAULT '',
                    headline TEXT NOT NULL DEFAULT '',
                    topics JSONB NOT NULL DEFAULT '[]'::jsonb,
                    dirty BOOLEAN NOT NULL DEFAULT TRUE,
                    regen_attempt_count INTEGER NOT NULL DEFAULT 0,
                    summary_version INTEGER NOT NULL DEFAULT 0,
                    last_regen_at TIMESTAMPTZ,
                    last_user_edit_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (namespace, id),
                    UNIQUE (namespace, entity_id)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS entity_pages_dirty ON entity_pages(namespace, dirty)")
            cur.execute("CREATE INDEX IF NOT EXISTS entity_pages_updated ON entity_pages(namespace, updated_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS entity_pages_last_regen ON entity_pages(namespace, last_regen_at)")

            # ----------------------------------------------------------
            # M4: thread active-entity LRU stack (D41a + D41b)
            # ----------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS thread_active_entities (
                    namespace TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    last_seen_at TIMESTAMPTZ NOT NULL,
                    source TEXT NOT NULL DEFAULT 'recall_hit',
                    PRIMARY KEY (namespace, thread_id, entity_id)
                )
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS thread_active_entities_seen "
                "ON thread_active_entities(namespace, thread_id, last_seen_at DESC)"
            )

            # ----------------------------------------------------------
            # M2: L4 Journal (append-only audit log)
            # ----------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS journal (
                    namespace TEXT NOT NULL,
                    id TEXT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    target_entity_id TEXT,
                    target_atom_id TEXT,
                    target_candidate_id TEXT,
                    before JSONB,
                    after JSONB,
                    note TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (namespace, id)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS journal_time ON journal(namespace, timestamp)")
            cur.execute("CREATE INDEX IF NOT EXISTS journal_action ON journal(namespace, action)")
            cur.execute("CREATE INDEX IF NOT EXISTS journal_target_entity ON journal(namespace, target_entity_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS journal_target_atom ON journal(namespace, target_atom_id)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS journal_target_candidate ON journal(namespace, target_candidate_id)"
            )
            # RISK-026 / ADR-025: journal is the highest-churn shared table
            # (every namespace's extract_run heartbeat + every real mutation
            # lands here); the default autovacuum_vacuum_scale_factor (0.2)
            # waits for dead tuples to reach 20% of table size, which is
            # conservative for a table this active. Loosening it here means
            # autovacuum reclaims journal space sooner on its own — no
            # scheduler needed, unlike the SQLite side of this story. See
            # pipeline/lifecycle/vacuum.py for the equivalent tuning of
            # LangGraph's checkpoint tables (those are third-party-owned,
            # so they can't be tuned from this DDL).
            cur.execute(
                "ALTER TABLE journal SET (autovacuum_vacuum_scale_factor = 0.05, autovacuum_vacuum_cost_delay = 2)"
            )

            # ----------------------------------------------------------
            # M5: L2.5 Episodes (situational/emotional diary layer)
            # ----------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    namespace TEXT NOT NULL,
                    id TEXT NOT NULL,
                    raw_event_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                    occurred_at TIMESTAMPTZ NOT NULL,
                    summary TEXT NOT NULL,
                    verbatim_quote TEXT NOT NULL,
                    quote_event_id TEXT NOT NULL,
                    emotion TEXT NOT NULL DEFAULT 'neutral',
                    intensity INTEGER NOT NULL DEFAULT 1,
                    people JSONB NOT NULL DEFAULT '[]'::jsonb,
                    topics JSONB NOT NULL DEFAULT '[]'::jsonb,
                    extractor_version TEXT NOT NULL,
                    session_id TEXT,
                    digest_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL,
                    fts_tsv TSVECTOR GENERATED ALWAYS AS (
                        to_tsvector(
                            'simple',
                            summary || ' ' || verbatim_quote || ' ' ||
                            COALESCE(jsonb_path_query_array(people, '$[*]')::text, '') || ' ' ||
                            COALESCE(jsonb_path_query_array(topics, '$[*]')::text, '')
                        )
                    ) STORED,
                    PRIMARY KEY (namespace, id)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS episodes_occurred ON episodes(namespace, occurred_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS episodes_session ON episodes(namespace, session_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS episodes_emotion ON episodes(namespace, emotion)")
            cur.execute("CREATE INDEX IF NOT EXISTS episodes_fts ON episodes USING GIN(fts_tsv)")

            # ----------------------------------------------------------
            # M5: Weekly/monthly digests of episodes
            # ----------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS digests (
                    namespace TEXT NOT NULL,
                    id TEXT NOT NULL,
                    period_kind TEXT NOT NULL,
                    period_key TEXT NOT NULL,
                    period_start TIMESTAMPTZ NOT NULL,
                    period_end TIMESTAMPTZ NOT NULL,
                    markdown TEXT NOT NULL,
                    episode_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                    llm_version TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (namespace, id),
                    UNIQUE (namespace, period_kind, period_key)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS digests_start ON digests(namespace, period_start)")

            self._scope_fts_indexes_by_namespace(cur)

        self._conn.commit()
        # Session-level: subsequent unqualified table names resolve to the
        # shared schema for this connection's lifetime.
        self._conn.execute(f"SET search_path TO {SHARED_SCHEMA}, public")
        self._conn.commit()

    def _scope_fts_indexes_by_namespace(self, cur: Any) -> None:
        """Replace single-column FTS indexes with ``(namespace, tsv)`` ones.

        All namespaces live in one set of tables, and every FTS query filters
        ``namespace = %s``. With a plain ``GIN(tsv)`` index Postgres matches the
        search term across *every* namespace first and only then intersects with
        the namespace filter, so one agent's recall cost grows with the whole
        install's corpus rather than its own.

        A composite ``GIN (namespace, tsv)`` needs the ``btree_gin`` extension.
        It is trusted since PG13, so a database owner can install it without
        superuser; where that still fails (locked-down role, extension not
        shipped) the single-column indexes are left in place and recall keeps
        working — just without namespace scoping.

        Runs under the caller's advisory lock, so concurrent instances cannot
        race the swap.
        """
        scoped_names = {f"{table}_fts_ns" for table, _column in _FTS_INDEXES}
        legacy_names = {f"{table}_fts" for table, _column in _FTS_INDEXES}
        cur.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = %s AND indexname = ANY(%s)",
            (SHARED_SCHEMA, list(scoped_names | legacy_names)),
        )
        existing = {str(row["indexname"]) for row in cur.fetchall()}
        missing_scoped = scoped_names - existing
        existing_legacy = legacy_names & existing
        if not missing_scoped and not existing_legacy:
            return
        if not self._enable_btree_gin():
            return
        for table, column in _FTS_INDEXES:
            scoped_name = f"{table}_fts_ns"
            legacy_name = f"{table}_fts"
            if scoped_name not in existing:
                cur.execute(f"CREATE INDEX IF NOT EXISTS {scoped_name} ON {table} USING GIN (namespace, {column})")
            # Redundant now: every FTS query is namespace-scoped.
            if legacy_name in existing:
                cur.execute(f"DROP INDEX IF EXISTS {legacy_name}")

    def _enable_btree_gin(self) -> bool:
        """Install ``btree_gin``, reporting whether it is usable.

        Wrapped in a savepoint: a privilege error must not abort the schema
        transaction that created the tables.
        """
        try:
            with self._conn.transaction(), self._conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")
        except psycopg.Error:
            logger.info(
                "btree_gin unavailable; keeping namespace-agnostic FTS indexes. "
                "Recall will match search terms across every namespace before "
                "filtering, which costs more as the install grows.",
                exc_info=True,
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Legacy migration (one-schema-per-namespace → shared tables)
    # ------------------------------------------------------------------

    def _legacy_schema_exists(self, cur: Any) -> bool:
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = 'raw_events'",
            (self._ns,),
        )
        return cur.fetchone() is not None

    def _legacy_has_uuid_ids(self, cur: Any) -> bool:
        """True when the legacy schema predates TEXT ids (data unusable)."""
        cur.execute(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'raw_events' AND column_name = 'id'
            """,
            (self._ns,),
        )
        row = cur.fetchone()
        if row is None:
            return False
        data_type = row["data_type"] if isinstance(row, dict) else row[0]
        return str(data_type).lower() == "uuid"

    def _copyable_columns(self, cur: Any, table: str) -> list[str]:
        """Columns present in BOTH legacy and shared table, minus generated/namespace."""
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s AND is_generated = 'NEVER'
            """,
            (self._ns, table),
        )
        legacy = {r["column_name"] for r in cur.fetchall()}
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s AND is_generated = 'NEVER'
              AND column_name <> 'namespace'
            """,
            (SHARED_SCHEMA, table),
        )
        shared = [r["column_name"] for r in cur.fetchall()]
        return [c for c in shared if c in legacy]

    def _migrate_legacy_schema(self) -> None:
        """Copy rows from a legacy per-namespace schema into the shared tables.

        Runs once: skipped when no legacy schema exists, when the legacy
        layout predates TEXT ids (nothing usable to copy), or when the shared
        tables already hold rows for this namespace. After a successful copy
        the legacy schema is renamed to ``{ns}__old`` as a backup — data is
        never dropped here.
        """
        ns = self._ns
        if ns == SHARED_SCHEMA:
            # A namespace literally named like the shared schema would make the
            # legacy probe match the shared tables themselves — never migrate.
            self._conn.commit()
            return
        with self._cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (_DDL_LOCK_KEY,))
            if not self._legacy_schema_exists(cur):
                self._conn.commit()
                return
            if self._legacy_has_uuid_ids(cur):
                logger.warning(
                    "legacy memory schema %r uses UUID ids (pre-TEXT layout); "
                    "skipping data copy and renaming it out of the way",
                    ns,
                )
                self._rename_legacy_schema(cur)
                self._conn.commit()
                return
            cur.execute("SELECT 1 FROM raw_events WHERE namespace = %s LIMIT 1", (ns,))
            already = cur.fetchone() is not None
            if not already:
                cur.execute("SELECT 1 FROM memory_nodes WHERE namespace = %s LIMIT 1", (ns,))
                already = cur.fetchone() is not None
            if already:
                logger.warning(
                    "shared memory tables already contain rows for namespace %r; "
                    "leaving legacy schema %r untouched (manual reconciliation needed)",
                    ns,
                    ns,
                )
                self._conn.commit()
                return

            cur.execute("SET CONSTRAINTS ALL DEFERRED")
            copied = 0
            for table in _TABLES:
                cur.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
                    (ns, table),
                )
                if cur.fetchone() is None:
                    continue
                cols = self._copyable_columns(cur, table)
                if not cols:
                    continue
                col_list = ", ".join(f'"{c}"' for c in cols)
                cur.execute(
                    f"INSERT INTO {SHARED_SCHEMA}.{table} (namespace, {col_list}) "
                    f"SELECT %s, {col_list} FROM {ns}.{table}",
                    (ns,),
                )
                copied += _rowcount(cur.rowcount)
            self._rename_legacy_schema(cur)
        self._conn.commit()
        logger.info("migrated legacy memory schema %r into shared tables (%d rows)", ns, copied)

    def _rename_legacy_schema(self, cur: Any) -> None:
        # PG identifiers cap at 63 bytes; keep room for the suffix.
        backup = f"{self._ns[:56]}__old"
        cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (backup,))
        if cur.fetchone() is not None:
            logger.warning(
                "backup schema %r already exists; leaving legacy schema %r in place",
                backup,
                self._ns,
            )
            return
        cur.execute(f"ALTER SCHEMA {self._ns} RENAME TO {backup}")

    # ------------------------------------------------------------------
    # Namespace lifecycle
    # ------------------------------------------------------------------

    def purge_namespace(self) -> int:
        """Delete every row belonging to this namespace across all tables.

        Returns the total number of rows deleted. The shared tables and
        other namespaces are untouched.
        """
        total = 0
        with self._cursor() as cur:
            # Children before parents: memory_nodes self-FK is the only one.
            cur.execute("SET CONSTRAINTS ALL DEFERRED")
            for table in _TABLES:
                cur.execute(f"DELETE FROM {table} WHERE namespace = %s", (self._ns,))
                total += _rowcount(cur.rowcount)
        return total

    # ------------------------------------------------------------------
    # Memory tree
    # ------------------------------------------------------------------

    def save_node(self, node: MemoryNode) -> None:
        """Strict insert. Re-inserting same id raises ``psycopg.errors.UniqueViolation``."""
        if node.level == "leaf" and node.atom_id is None:
            raise ValueError("leaf nodes must reference an AtomCard via atom_id")
        if node.level != "leaf" and node.atom_id is not None:
            raise ValueError("root and branch nodes cannot reference an AtomCard")
        stored_content = "" if node.level == "leaf" and node.atom_id is not None else node.content
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO memory_nodes
                    (namespace, id, parent_id, level, atom_id, content, topic, conversation_id,
                     created_at, updated_at, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    self._ns,
                    node.id,
                    node.parent_id,
                    node.level,
                    node.atom_id,
                    stored_content,
                    node.topic,
                    node.conversation_id,
                    node.created_at,
                    node.updated_at,
                    Jsonb(node.metadata),
                ),
            )

    def get_node(self, node_id: str) -> MemoryNode | None:
        with self._cursor() as cur:
            cur.execute(
                """SELECT n.*, a.assertion AS atom_content
                    FROM memory_nodes n
                    LEFT JOIN atoms a ON a.namespace = n.namespace AND a.id = n.atom_id
                    WHERE n.namespace = %s AND n.id = %s""",
                (self._ns, node_id),
            )
            row = cur.fetchone()
        return self._row_to_node(row) if row else None

    def get_node_by_atom_id(self, atom_id: str) -> MemoryNode | None:
        """Fetch the leaf node that references ``atom_id``, or ``None``."""
        with self._cursor() as cur:
            cur.execute(
                """SELECT n.*, a.assertion AS atom_content
                    FROM memory_nodes n
                    LEFT JOIN atoms a ON a.namespace = n.namespace AND a.id = n.atom_id
                    WHERE n.namespace = %s AND n.atom_id = %s""",
                (self._ns, atom_id),
            )
            row = cur.fetchone()
        return self._row_to_node(row) if row else None

    def get_children(self, parent_id: str | None) -> list[MemoryNode]:
        with self._cursor() as cur:
            if parent_id is None:
                cur.execute(
                    """SELECT n.*, a.assertion AS atom_content
                        FROM memory_nodes n
                        LEFT JOIN atoms a ON a.namespace = n.namespace AND a.id = n.atom_id
                        WHERE n.namespace = %s AND n.parent_id IS NULL""",
                    (self._ns,),
                )
            else:
                cur.execute(
                    """SELECT n.*, a.assertion AS atom_content
                        FROM memory_nodes n
                        LEFT JOIN atoms a ON a.namespace = n.namespace AND a.id = n.atom_id
                        WHERE n.namespace = %s AND n.parent_id = %s""",
                    (self._ns, parent_id),
                )
            rows = cur.fetchall()
        return [self._row_to_node(r) for r in rows]

    def update_node(
        self,
        node_id: str,
        *,
        content: str | None = None,
        topic: str | _Unset | None = _UNSET,
        metadata: dict[str, Any] | _Unset | None = _UNSET,
    ) -> bool:
        """Update mutable fields. ``parent_id`` / ``level`` are immutable here.

        ``metadata`` semantics is **replace** (whole-dict overwrite).
        Returns ``True`` if the node existed and was updated.
        """
        sets: list[str] = []
        params: list[Any] = []
        if content is not None:
            sets.append("content = %s")
            params.append(content)
        if not isinstance(topic, _Unset):
            sets.append("topic = %s")
            params.append(topic)
        if not isinstance(metadata, _Unset):
            sets.append("metadata = %s")
            params.append(Jsonb(metadata or {}))

        with self._cursor() as cur:
            if not sets:
                cur.execute(
                    "SELECT 1 FROM memory_nodes WHERE namespace = %s AND id = %s",
                    (self._ns, node_id),
                )
                return cur.fetchone() is not None

            sets.append("updated_at = %s")
            params.append(datetime.now(UTC))
            params.append(self._ns)
            params.append(node_id)
            cur.execute(
                f"UPDATE memory_nodes SET {', '.join(sets)} WHERE namespace = %s AND id = %s",
                params,
            )
            updated = _rowcount(cur.rowcount) > 0
        return updated

    def delete_node(self, node_id: str, *, cascade: bool = False) -> bool:
        """Delete node. Without ``cascade`` and with children → raises ValueError.

        Cascade is implemented in the service layer here (not via FK
        ``ON DELETE CASCADE``) for parity with SQLite.
        """
        with self._cursor() as cur:
            cur.execute(
                "SELECT 1 FROM memory_nodes WHERE namespace = %s AND id = %s",
                (self._ns, node_id),
            )
            if cur.fetchone() is None:
                return False

            if cascade:
                # Walk subtree iteratively (BFS).
                to_delete: list[str] = []
                frontier: list[str] = [node_id]
                while frontier:
                    cur.execute(
                        "SELECT id FROM memory_nodes WHERE namespace = %s AND parent_id = ANY(%s)",
                        (self._ns, frontier),
                    )
                    child_rows = cur.fetchall()
                    to_delete.extend(frontier)
                    frontier = [str(r["id"]) for r in child_rows]
                cur.execute(
                    "DELETE FROM memory_nodes WHERE namespace = %s AND id = ANY(%s)",
                    (self._ns, to_delete),
                )
            else:
                cur.execute(
                    "SELECT COUNT(*) AS c FROM memory_nodes WHERE namespace = %s AND parent_id = %s",
                    (self._ns, node_id),
                )
                count_row = cur.fetchone()
                child_count = int(count_row["c"]) if count_row is not None else 0
                if child_count > 0:
                    raise ValueError(
                        f"Node {node_id!r} has {child_count} child(ren); pass cascade=True to delete subtree."
                    )
                cur.execute(
                    "DELETE FROM memory_nodes WHERE namespace = %s AND id = %s",
                    (self._ns, node_id),
                )
        return True

    def search_memories(self, query: str, limit: int = 5) -> list[MemoryNode]:
        with self._cursor() as cur:
            cur.execute(
                """SELECT n.*, a.assertion AS atom_content
                    FROM atoms a
                    JOIN memory_nodes n ON n.namespace = a.namespace AND n.atom_id = a.id
                    WHERE a.namespace = %s
                      AND a.fts_tsv @@ plainto_tsquery('simple', %s)
                      AND a.deprecated_at IS NULL
                    ORDER BY ts_rank(a.fts_tsv, plainto_tsquery('simple', %s)) DESC
                    LIMIT %s""",
                (self._ns, query, query, limit),
            )
            rows = cur.fetchall()
        return [self._row_to_node(r) for r in rows]

    def get_tree(self) -> list[MemoryNode]:
        with self._cursor() as cur:
            cur.execute(
                """SELECT n.*, a.assertion AS atom_content
                    FROM memory_nodes n
                    LEFT JOIN atoms a ON a.namespace = n.namespace AND a.id = n.atom_id
                    WHERE n.namespace = %s""",
                (self._ns,),
            )
            rows = cur.fetchall()
        return [self._row_to_node(r) for r in rows]

    # ------------------------------------------------------------------
    # L0 Raw events (M1)
    # ------------------------------------------------------------------

    def save_raw(self, event: RawEvent) -> None:
        """Append a raw event. Strict insert; duplicate id → UniqueViolation."""
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO raw_events
                    (namespace, id, host, session_id, thread_id, "user", timestamp,
                     event_type, content, payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    self._ns,
                    event.id,
                    event.host,
                    event.session_id,
                    event.thread_id,
                    event.user,
                    event.timestamp,
                    event.event_type,
                    event.content,
                    Jsonb(event.payload),
                ),
            )

    def save_raw_batch(self, events: list[RawEvent]) -> None:
        if not events:
            return
        rows = [
            (
                self._ns,
                e.id,
                e.host,
                e.session_id,
                e.thread_id,
                e.user,
                e.timestamp,
                e.event_type,
                e.content,
                Jsonb(e.payload),
            )
            for e in events
        ]
        with self._cursor() as cur:
            cur.executemany(
                """INSERT INTO raw_events
                    (namespace, id, host, session_id, thread_id, "user", timestamp,
                     event_type, content, payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )

    def get_raw(self, event_id: str) -> RawEvent | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM raw_events WHERE namespace = %s AND id = %s",
                (self._ns, event_id),
            )
            row = cur.fetchone()
        return self._row_to_raw(row) if row else None

    def list_raw(
        self,
        *,
        host: str | None = None,
        session_id: str | None = None,
        thread_id: str | None = None,
        user: str | None = None,
        event_type: RawEventType | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[RawEvent]:
        conditions: list[str] = ["namespace = %s"]
        params: list[Any] = [self._ns]
        if host is not None:
            conditions.append("host = %s")
            params.append(host)
        if session_id is not None:
            conditions.append("session_id = %s")
            params.append(session_id)
        if thread_id is not None:
            conditions.append("thread_id = %s")
            params.append(thread_id)
        if user is not None:
            conditions.append('"user" = %s')
            params.append(user)
        if event_type is not None:
            conditions.append("event_type = %s")
            params.append(event_type)
        if after is not None:
            conditions.append("timestamp >= %s")
            params.append(after)
        if before is not None:
            conditions.append("timestamp <= %s")
            params.append(before)

        where = f"WHERE {' AND '.join(conditions)}"
        params.append(limit)

        with self._cursor() as cur:
            cur.execute(
                f"""SELECT * FROM raw_events
                    {where}
                    ORDER BY timestamp DESC
                    LIMIT %s""",
                params,
            )
            rows = cur.fetchall()
        return [self._row_to_raw(r) for r in rows]

    def search_raw(self, query: str, *, limit: int = 10) -> list[RawEvent]:
        with self._cursor() as cur:
            cur.execute(
                """SELECT * FROM raw_events
                    WHERE namespace = %s
                      AND content_tsv @@ plainto_tsquery('simple', %s)
                    ORDER BY ts_rank(content_tsv, plainto_tsquery('simple', %s)) DESC
                    LIMIT %s""",
                (self._ns, query, query, limit),
            )
            rows = cur.fetchall()
        return [self._row_to_raw(r) for r in rows]

    def delete_raw_before(self, before: datetime) -> int:
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM raw_events WHERE namespace = %s AND timestamp < %s",
                (self._ns, before),
            )
            count = _rowcount(cur.rowcount)
        return count

    def get_raw_events_by_ids(self, event_ids: list[str]) -> list[RawEvent]:
        """Batch-fetch raw events by a list of IDs (used to obtain occurred_at)."""
        if not event_ids:
            return []
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM raw_events WHERE namespace = %s AND id = ANY(%s)",
                (self._ns, list(event_ids)),
            )
            rows = cur.fetchall()
        return [self._row_to_raw(r) for r in rows]

    # ------------------------------------------------------------------
    # M2 — Candidates
    # ------------------------------------------------------------------

    def find_duplicate_candidate(
        self,
        assertion: str,
        raw_event_ids: list[str],
        subject_name: str | None = None,
    ) -> bool:
        """True when a ``promoted`` candidate with identical assertion + subject_name + raw_event_ids already exists.

        Mirrors the SQLite backend: only ``promoted`` rows are considered so
        still-``pending`` duplicates (test scenarios) are not skipped. The
        raw_event_ids set is compared in Python to stay order-insensitive.
        """
        if not raw_event_ids:
            return False
        target_ids = frozenset(raw_event_ids)
        with self._cursor() as cur:
            cur.execute(
                """SELECT raw_event_ids FROM candidates
                    WHERE namespace = %s AND assertion = %s AND subject_name = %s
                      AND status = 'promoted'""",
                (self._ns, assertion, subject_name),
            )
            rows = cur.fetchall()
        for row in rows:
            existing = self._coerce_jsonb(row["raw_event_ids"])
            if existing and frozenset(existing) == target_ids:
                return True
        return False

    def save_candidate(self, candidate: Candidate) -> None:
        """Insert a new candidate. Strict insert; duplicate id → UniqueViolation."""
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO candidates
                    (namespace, id, raw_event_ids, candidate_type, status, title,
                     assertion, verbatim_quote, quote_event_id,
                     subject_name, subject_entity_type, target_entity_id,
                     confidence, importance, recommended_action,
                     promotion_reason, extractor_version,
                     created_at, decided_at, decided_by, session_id, payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    self._ns,
                    candidate.id,
                    Jsonb(candidate.raw_event_ids),
                    candidate.candidate_type,
                    candidate.status,
                    candidate.title,
                    candidate.assertion,
                    candidate.verbatim_quote,
                    candidate.quote_event_id,
                    candidate.subject_name,
                    candidate.subject_entity_type,
                    candidate.target_entity_id,
                    candidate.confidence,
                    candidate.importance,
                    candidate.recommended_action,
                    candidate.promotion_reason,
                    candidate.extractor_version,
                    candidate.created_at,
                    candidate.decided_at,
                    candidate.decided_by,
                    candidate.session_id,
                    Jsonb(candidate.payload),
                ),
            )

    def get_candidate(self, candidate_id: str) -> Candidate | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM candidates WHERE namespace = %s AND id = %s",
                (self._ns, candidate_id),
            )
            row = cur.fetchone()
        return self._row_to_candidate(row) if row else None

    def list_candidates(
        self,
        *,
        status: CandidateStatus | None = None,
        session_id: str | None = None,
        target_entity_id: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[Candidate]:
        conditions: list[str] = ["namespace = %s"]
        params: list[Any] = [self._ns]
        if status is not None:
            conditions.append("status = %s")
            params.append(status)
        if session_id is not None:
            conditions.append("session_id = %s")
            params.append(session_id)
        if target_entity_id is not None:
            conditions.append("target_entity_id = %s")
            params.append(target_entity_id)
        if after is not None:
            conditions.append("created_at >= %s")
            params.append(after)
        if before is not None:
            conditions.append("created_at <= %s")
            params.append(before)

        where = f"WHERE {' AND '.join(conditions)}"
        params.append(limit)

        with self._cursor() as cur:
            cur.execute(
                f"""SELECT * FROM candidates
                    {where}
                    ORDER BY created_at DESC
                    LIMIT %s""",
                params,
            )
            rows = cur.fetchall()
        return [self._row_to_candidate(r) for r in rows]

    def update_candidate_status(
        self,
        candidate_id: str,
        *,
        status: CandidateStatus,
        decided_by: str | None = None,
        decided_at: datetime | None = None,
        target_entity_id: str | _Unset | None = _UNSET,
        promotion_reason: str | None = None,
    ) -> bool:
        sets: list[str] = ["status = %s"]
        params: list[Any] = [status]

        if decided_by is not None:
            sets.append("decided_by = %s")
            params.append(decided_by)
        if decided_at is not None:
            sets.append("decided_at = %s")
            params.append(decided_at)
        if not isinstance(target_entity_id, _Unset):
            sets.append("target_entity_id = %s")
            params.append(target_entity_id)
        if promotion_reason is not None:
            sets.append("promotion_reason = %s")
            params.append(promotion_reason)

        params.append(self._ns)
        params.append(candidate_id)

        with self._cursor() as cur:
            cur.execute(
                f"UPDATE candidates SET {', '.join(sets)} WHERE namespace = %s AND id = %s",
                params,
            )
            count = _rowcount(cur.rowcount)
        return count > 0

    def search_candidates(self, query: str, *, limit: int = 10) -> list[Candidate]:
        with self._cursor() as cur:
            cur.execute(
                """SELECT * FROM candidates
                    WHERE namespace = %s
                      AND fts_tsv @@ plainto_tsquery('simple', %s)
                    ORDER BY ts_rank(fts_tsv, plainto_tsquery('simple', %s)) DESC
                    LIMIT %s""",
                (self._ns, query, query, limit),
            )
            rows = cur.fetchall()
        return [self._row_to_candidate(r) for r in rows]

    # ------------------------------------------------------------------
    # M2 — Atoms
    # ------------------------------------------------------------------

    def save_atom(self, atom: AtomCard) -> None:
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO atoms
                    (namespace, id, entity_id, candidate_id, raw_event_ids,
                     assertion, verbatim_quote, quote_event_id, search_terms,
                     occurred_at, confidence, importance,
                     superseded_by, deprecated_at, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    self._ns,
                    atom.id,
                    atom.entity_id,
                    atom.candidate_id,
                    Jsonb(atom.raw_event_ids),
                    atom.assertion,
                    atom.verbatim_quote,
                    atom.quote_event_id,
                    Jsonb(atom.search_terms),
                    atom.occurred_at,
                    atom.confidence,
                    atom.importance,
                    atom.superseded_by,
                    atom.deprecated_at,
                    atom.created_at,
                ),
            )

    def get_atom(self, atom_id: str) -> AtomCard | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM atoms WHERE namespace = %s AND id = %s",
                (self._ns, atom_id),
            )
            row = cur.fetchone()
        return self._row_to_atom(row) if row else None

    def list_atoms(
        self,
        *,
        entity_id: str | None = None,
        importance: ImportanceLevel | None = None,
        include_deprecated: bool = False,
        limit: int = 100,
    ) -> list[AtomCard]:
        conditions: list[str] = ["namespace = %s"]
        params: list[Any] = [self._ns]
        if entity_id is not None:
            conditions.append("entity_id = %s")
            params.append(entity_id)
        if importance is not None:
            conditions.append("importance = %s")
            params.append(importance)
        if not include_deprecated:
            conditions.append("deprecated_at IS NULL")

        where = f"WHERE {' AND '.join(conditions)}"
        params.append(limit)

        with self._cursor() as cur:
            cur.execute(
                f"""SELECT * FROM atoms
                    {where}
                    ORDER BY created_at DESC
                    LIMIT %s""",
                params,
            )
            rows = cur.fetchall()
        return [self._row_to_atom(r) for r in rows]

    def supersede_atom(
        self,
        old_atom_id: str,
        *,
        new_atom_id: str,
        deprecated_at: datetime,
    ) -> bool:
        with self._cursor() as cur:
            cur.execute(
                """UPDATE atoms
                    SET superseded_by = %s, deprecated_at = %s
                    WHERE namespace = %s AND id = %s AND deprecated_at IS NULL""",
                (new_atom_id, deprecated_at, self._ns, old_atom_id),
            )
            count = _rowcount(cur.rowcount)
        return count > 0

    def deprecate_atom(self, atom_id: str, *, deprecated_at: datetime) -> bool:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE atoms SET deprecated_at = %s WHERE namespace = %s AND id = %s",
                (deprecated_at, self._ns, atom_id),
            )
            count = _rowcount(cur.rowcount)
        return count > 0

    def search_atoms(
        self,
        query: str,
        *,
        include_deprecated: bool = False,
        limit: int = 10,
    ) -> list[AtomCard]:
        deprecation_filter = "" if include_deprecated else "AND deprecated_at IS NULL"
        with self._cursor() as cur:
            cur.execute(
                f"""SELECT * FROM atoms
                    WHERE namespace = %s
                      AND fts_tsv @@ plainto_tsquery('simple', %s)
                      {deprecation_filter}
                    ORDER BY ts_rank(fts_tsv, plainto_tsquery('simple', %s)) DESC
                    LIMIT %s""",
                (self._ns, query, query, limit),
            )
            rows = cur.fetchall()
        return [self._row_to_atom(r) for r in rows]

    def search_atoms_by_time_range(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        entity_id: str | None = None,
        include_deprecated: bool = False,
        limit: int = 50,
    ) -> list[AtomCard]:
        clauses: list[str] = ["namespace = %s"]
        params: list[object] = [self._ns]
        if start is not None:
            clauses.append("occurred_at >= %s")
            params.append(start)
        if end is not None:
            clauses.append("occurred_at <= %s")
            params.append(end)
        if entity_id is not None:
            clauses.append("entity_id = %s")
            params.append(entity_id)
        if not include_deprecated:
            clauses.append("deprecated_at IS NULL")
        where = "WHERE " + " AND ".join(clauses)
        params.append(limit)
        with self._cursor() as cur:
            cur.execute(
                f"""SELECT * FROM atoms
                    {where}
                    ORDER BY occurred_at DESC
                    LIMIT %s""",
                params,
            )
            rows = cur.fetchall()
        return [self._row_to_atom(r) for r in rows]

    def find_atom_by_signature(self, signature: str) -> AtomCard | None:
        """Find the first non-deprecated atom whose assertion signature matches.

        Signatures are compared in Python (via ``normalize_alias``) rather than
        in SQL, mirroring the SQLite backend, so collation differences can't
        cause false mismatches. LIMIT 200 bounds the scan.
        """
        from octop_memory.domain.alias import normalize_alias

        with self._cursor() as cur:
            cur.execute(
                """SELECT * FROM atoms
                    WHERE namespace = %s AND deprecated_at IS NULL
                    ORDER BY created_at ASC
                    LIMIT 200""",
                (self._ns,),
            )
            rows = cur.fetchall()
        for r in rows:
            atom = self._row_to_atom(r)
            if normalize_alias(atom.assertion) == signature:
                return atom
        return None

    def migrate_atoms_to_entity(
        self,
        source_entity_id: str,
        target_entity_id: str,
    ) -> int:
        """Bulk-migrate every non-deprecated atom under the source entity to the target entity, in a single transaction.

        Any atom whose assertion signature collides with an existing keeper
        under the target entity is deprecated (``superseded_by`` -> keeper)
        instead of migrated. Returns the number of atoms actually migrated.
        """
        from octop_memory.domain.alias import normalize_alias

        now = datetime.now(UTC)
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM atoms WHERE namespace = %s AND entity_id = %s AND deprecated_at IS NULL",
                (self._ns, source_entity_id),
            )
            source_atoms = cur.fetchall()
            if not source_atoms:
                return 0
            cur.execute(
                "SELECT * FROM atoms WHERE namespace = %s AND entity_id = %s AND deprecated_at IS NULL",
                (self._ns, target_entity_id),
            )
            target_atoms = cur.fetchall()

        target_sig_map: dict[str, str] = {}
        for r in target_atoms:
            atom = self._row_to_atom(r)
            sig = normalize_alias(atom.assertion)
            if sig and sig not in target_sig_map:
                target_sig_map[sig] = atom.id

        migrated = 0
        with self.transaction(), self._conn.cursor() as cur:
            for r in source_atoms:
                atom = self._row_to_atom(r)
                sig = normalize_alias(atom.assertion)
                if sig and sig in target_sig_map:
                    keeper_id = target_sig_map[sig]
                    cur.execute(
                        """UPDATE atoms SET superseded_by = %s, deprecated_at = %s
                            WHERE namespace = %s AND id = %s""",
                        (keeper_id, now, self._ns, atom.id),
                    )
                else:
                    cur.execute(
                        "UPDATE atoms SET entity_id = %s WHERE namespace = %s AND id = %s",
                        (target_entity_id, self._ns, atom.id),
                    )
                    if sig:
                        target_sig_map[sig] = atom.id
                    migrated += 1
        return migrated

    # ------------------------------------------------------------------
    # M2 — Entities
    # ------------------------------------------------------------------

    def save_entity(self, entity: Entity) -> None:
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO entities
                    (namespace, id, entity_type, canonical_name, aliases,
                     atom_count, last_promoted_at, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    self._ns,
                    entity.id,
                    entity.entity_type,
                    entity.canonical_name,
                    Jsonb(entity.aliases),
                    entity.atom_count,
                    entity.last_promoted_at,
                    entity.created_at,
                ),
            )

    def get_entity(self, entity_id: str) -> Entity | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM entities WHERE namespace = %s AND id = %s",
                (self._ns, entity_id),
            )
            row = cur.fetchone()
        return self._row_to_entity(row) if row else None

    def find_entity_by_name(
        self,
        canonical_name: str,
        *,
        entity_type: EntityType | None = None,
    ) -> Entity | None:
        with self._cursor() as cur:
            if entity_type is not None:
                cur.execute(
                    """SELECT * FROM entities
                        WHERE namespace = %s
                          AND LOWER(canonical_name) = LOWER(%s) AND entity_type = %s
                        LIMIT 1""",
                    (self._ns, canonical_name, entity_type),
                )
            else:
                cur.execute(
                    """SELECT * FROM entities
                        WHERE namespace = %s
                          AND LOWER(canonical_name) = LOWER(%s)
                        LIMIT 1""",
                    (self._ns, canonical_name),
                )
            row = cur.fetchone()
        return self._row_to_entity(row) if row else None

    def list_entities(
        self,
        *,
        entity_type: EntityType | None = None,
        limit: int = 100,
    ) -> list[Entity]:
        with self._cursor() as cur:
            if entity_type is not None:
                cur.execute(
                    """SELECT * FROM entities
                        WHERE namespace = %s AND entity_type = %s
                        ORDER BY canonical_name
                        LIMIT %s""",
                    (self._ns, entity_type, limit),
                )
            else:
                cur.execute(
                    """SELECT * FROM entities
                        WHERE namespace = %s
                        ORDER BY canonical_name
                        LIMIT %s""",
                    (self._ns, limit),
                )
            rows = cur.fetchall()
        return [self._row_to_entity(r) for r in rows]

    def bump_entity_atom_count(
        self,
        entity_id: str,
        *,
        delta: int,
        last_promoted_at: datetime | None = None,
    ) -> bool:
        with self._cursor() as cur:
            if last_promoted_at is not None:
                cur.execute(
                    """UPDATE entities
                        SET atom_count = atom_count + %s,
                            last_promoted_at = %s
                        WHERE namespace = %s AND id = %s""",
                    (delta, last_promoted_at, self._ns, entity_id),
                )
            else:
                cur.execute(
                    """UPDATE entities
                        SET atom_count = atom_count + %s
                        WHERE namespace = %s AND id = %s""",
                    (delta, self._ns, entity_id),
                )
            count = _rowcount(cur.rowcount)
        return count > 0

    def update_entity_canonical_name(self, entity_id: str, canonical_name: str) -> bool:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE entities SET canonical_name = %s WHERE namespace = %s AND id = %s",
                (canonical_name, self._ns, entity_id),
            )
            count = _rowcount(cur.rowcount)
        return count > 0

    # ------------------------------------------------------------------
    # M2 — Aliases
    # ------------------------------------------------------------------

    def save_alias(self, alias: Alias) -> None:
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO aliases
                    (namespace, alias, entity_id, entity_type, created_by, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (namespace, alias, entity_id) DO NOTHING""",
                (
                    self._ns,
                    alias.alias,
                    alias.entity_id,
                    alias.entity_type,
                    alias.created_by,
                    alias.created_at,
                ),
            )

    def find_entity_by_alias(self, alias: str) -> Entity | None:
        with self._cursor() as cur:
            cur.execute(
                """SELECT e.* FROM aliases a
                    JOIN entities e ON e.namespace = a.namespace AND e.id = a.entity_id
                    WHERE a.namespace = %s AND a.alias = %s
                    LIMIT 1""",
                (self._ns, alias),
            )
            row = cur.fetchone()
        return self._row_to_entity(row) if row else None

    def list_aliases(
        self,
        *,
        entity_id: str | None = None,
        limit: int = 100,
    ) -> list[Alias]:
        with self._cursor() as cur:
            if entity_id is not None:
                cur.execute(
                    """SELECT * FROM aliases
                        WHERE namespace = %s AND entity_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s""",
                    (self._ns, entity_id, limit),
                )
            else:
                cur.execute(
                    """SELECT * FROM aliases
                        WHERE namespace = %s
                        ORDER BY created_at DESC
                        LIMIT %s""",
                    (self._ns, limit),
                )
            rows = cur.fetchall()
        return [self._row_to_alias(r) for r in rows]

    # ------------------------------------------------------------------
    # M3 - Entity Pages (long-form summary; D32-D37)
    # ------------------------------------------------------------------

    def upsert_entity_page(self, page: EntityPage) -> None:
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO entity_pages
                    (namespace, id, entity_id, summary_markdown, headline, topics,
                     dirty, regen_attempt_count, summary_version,
                     last_regen_at, last_user_edit_at,
                     created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (namespace, entity_id) DO UPDATE SET
                        summary_markdown = EXCLUDED.summary_markdown,
                        headline = EXCLUDED.headline,
                        topics = EXCLUDED.topics,
                        dirty = EXCLUDED.dirty,
                        regen_attempt_count = EXCLUDED.regen_attempt_count,
                        summary_version = EXCLUDED.summary_version,
                        last_regen_at = EXCLUDED.last_regen_at,
                        last_user_edit_at = EXCLUDED.last_user_edit_at,
                        updated_at = EXCLUDED.updated_at
                """,
                (
                    self._ns,
                    page.id,
                    page.entity_id,
                    page.summary_markdown,
                    page.headline,
                    Jsonb(page.topics),
                    page.dirty,
                    page.regen_attempt_count,
                    page.summary_version,
                    page.last_regen_at,
                    page.last_user_edit_at,
                    page.created_at,
                    page.updated_at,
                ),
            )

    def get_entity_page(self, entity_id: str) -> EntityPage | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM entity_pages WHERE namespace = %s AND entity_id = %s",
                (self._ns, entity_id),
            )
            row = cur.fetchone()
        return self._row_to_entity_page(row) if row else None

    def count_stats(self) -> dict[str, int]:
        out: dict[str, int] = {}
        with self._cursor() as cur:
            for key, sql in (
                ("raw_events", "SELECT COUNT(*) AS c FROM raw_events WHERE namespace = %s"),
                ("atoms", "SELECT COUNT(*) AS c FROM atoms WHERE namespace = %s"),
                ("entities", "SELECT COUNT(*) AS c FROM entities WHERE namespace = %s"),
                (
                    "dirty_pages",
                    "SELECT COUNT(*) AS c FROM entity_pages WHERE namespace = %s AND dirty = TRUE",
                ),
            ):
                cur.execute(sql, (self._ns,))
                row = cur.fetchone()
                # dict_row factory: COUNT comes back keyed, not positional.
                out[key] = int(row["c"]) if row else 0
        return out

    def list_dirty_entity_pages(self, *, limit: int = 50) -> list[EntityPage]:
        with self._cursor() as cur:
            cur.execute(
                """SELECT * FROM entity_pages
                    WHERE namespace = %s AND dirty = TRUE
                    ORDER BY (last_regen_at IS NULL) DESC,
                             last_regen_at ASC NULLS FIRST,
                             updated_at ASC
                    LIMIT %s""",
                (self._ns, limit),
            )
            rows = cur.fetchall()
        return [self._row_to_entity_page(r) for r in rows]

    def mark_entity_page_dirty(self, entity_id: str, *, when: datetime) -> None:
        with self._cursor() as cur:
            cur.execute(
                """UPDATE entity_pages
                    SET dirty = TRUE, updated_at = %s
                    WHERE namespace = %s AND entity_id = %s""",
                (when, self._ns, entity_id),
            )
            if _rowcount(cur.rowcount) == 0:
                cur.execute(
                    """INSERT INTO entity_pages
                        (namespace, id, entity_id, summary_markdown, headline, topics,
                         dirty, regen_attempt_count, summary_version,
                         last_regen_at, last_user_edit_at,
                         created_at, updated_at)
                        VALUES (%s, %s, %s, '', '', %s, TRUE, 0, 0, NULL, NULL, %s, %s)
                        ON CONFLICT (namespace, entity_id) DO UPDATE SET
                            dirty = TRUE,
                            updated_at = EXCLUDED.updated_at
                    """,
                    (
                        self._ns,
                        f"page_{entity_id}",
                        entity_id,
                        Jsonb([]),
                        when,
                        when,
                    ),
                )

    def apply_entity_page_regen(
        self,
        entity_id: str,
        *,
        summary_markdown: str,
        headline: str,
        topics: list[str],
        when: datetime,
    ) -> bool:
        with self._cursor() as cur:
            cur.execute(
                """UPDATE entity_pages
                    SET summary_markdown = %s,
                        headline = %s,
                        topics = %s,
                        dirty = FALSE,
                        regen_attempt_count = 0,
                        summary_version = summary_version + 1,
                        last_regen_at = %s,
                        updated_at = %s
                    WHERE namespace = %s AND entity_id = %s""",
                (
                    summary_markdown,
                    headline,
                    Jsonb(topics),
                    when,
                    when,
                    self._ns,
                    entity_id,
                ),
            )
            count = _rowcount(cur.rowcount)
        return count > 0

    def record_entity_page_regen_failure(
        self,
        entity_id: str,
        *,
        when: datetime,
    ) -> bool:
        with self._cursor() as cur:
            cur.execute(
                """UPDATE entity_pages
                    SET regen_attempt_count = regen_attempt_count + 1,
                        dirty = TRUE,
                        updated_at = %s
                    WHERE namespace = %s AND entity_id = %s""",
                (when, self._ns, entity_id),
            )
            count = _rowcount(cur.rowcount)
        return count > 0

    def apply_entity_page_user_edit(
        self,
        entity_id: str,
        *,
        summary_markdown: str,
        when: datetime,
    ) -> bool:
        with self._cursor() as cur:
            cur.execute(
                """UPDATE entity_pages
                    SET summary_markdown = %s,
                        summary_version = summary_version + 1,
                        last_user_edit_at = %s,
                        updated_at = %s
                    WHERE namespace = %s AND entity_id = %s""",
                (summary_markdown, when, when, self._ns, entity_id),
            )
            count = _rowcount(cur.rowcount)
        return count > 0

    # ------------------------------------------------------------------
    # M4 — Thread Active-Entity Stack (D41a + D41b)
    # ------------------------------------------------------------------

    def upsert_active_entity(self, record: ActiveEntity) -> None:
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO thread_active_entities
                    (namespace, thread_id, entity_id, last_seen_at, source)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (namespace, thread_id, entity_id) DO UPDATE SET
                        last_seen_at = EXCLUDED.last_seen_at,
                        source = EXCLUDED.source
                """,
                (
                    self._ns,
                    record.thread_id,
                    record.entity_id,
                    record.last_seen_at,
                    record.source,
                ),
            )

    def list_active_entities(
        self,
        thread_id: str,
        *,
        limit: int = 5,
    ) -> list[ActiveEntity]:
        with self._cursor() as cur:
            cur.execute(
                """SELECT thread_id, entity_id, last_seen_at, source
                    FROM thread_active_entities
                    WHERE namespace = %s AND thread_id = %s
                    ORDER BY last_seen_at DESC
                    LIMIT %s""",
                (self._ns, thread_id, limit),
            )
            rows = cur.fetchall()
        return [self._row_to_active_entity(r) for r in rows]

    def evict_active_entities(
        self,
        thread_id: str,
        *,
        keep: int = 5,
    ) -> int:
        with self._cursor() as cur:
            cur.execute(
                """DELETE FROM thread_active_entities
                    WHERE namespace = %s AND thread_id = %s
                      AND entity_id NOT IN (
                        SELECT entity_id FROM thread_active_entities
                        WHERE namespace = %s AND thread_id = %s
                        ORDER BY last_seen_at DESC
                        LIMIT %s
                      )""",
                (self._ns, thread_id, self._ns, thread_id, keep),
            )
            count = _rowcount(cur.rowcount)
        return count

    @staticmethod
    def _row_to_active_entity(row: dict[str, Any]) -> ActiveEntity:
        return ActiveEntity(
            thread_id=str(row["thread_id"]),
            entity_id=str(row["entity_id"]),
            last_seen_at=row["last_seen_at"],
            source=row.get("source") or "recall_hit",
        )

    # ------------------------------------------------------------------
    # M2 — Journal
    # ------------------------------------------------------------------

    def append_journal(self, entry: JournalEntry) -> None:
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO journal
                    (namespace, id, timestamp, action, actor,
                     target_entity_id, target_atom_id, target_candidate_id,
                     before, after, note)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    self._ns,
                    entry.id,
                    entry.timestamp,
                    entry.action,
                    entry.actor,
                    entry.target_entity_id,
                    entry.target_atom_id,
                    entry.target_candidate_id,
                    Jsonb(entry.before) if entry.before is not None else None,
                    Jsonb(entry.after) if entry.after is not None else None,
                    entry.note,
                ),
            )

    def list_journal(
        self,
        *,
        action: JournalAction | None = None,
        target_entity_id: str | None = None,
        target_atom_id: str | None = None,
        target_candidate_id: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[JournalEntry]:
        conditions: list[str] = ["namespace = %s"]
        params: list[Any] = [self._ns]
        if action is not None:
            conditions.append("action = %s")
            params.append(action)
        if target_entity_id is not None:
            conditions.append("target_entity_id = %s")
            params.append(target_entity_id)
        if target_atom_id is not None:
            conditions.append("target_atom_id = %s")
            params.append(target_atom_id)
        if target_candidate_id is not None:
            conditions.append("target_candidate_id = %s")
            params.append(target_candidate_id)
        if after is not None:
            conditions.append("timestamp >= %s")
            params.append(after)
        if before is not None:
            conditions.append("timestamp <= %s")
            params.append(before)

        where = f"WHERE {' AND '.join(conditions)}"
        params.append(limit)

        with self._cursor() as cur:
            cur.execute(
                f"""SELECT * FROM journal
                    {where}
                    ORDER BY timestamp DESC
                    LIMIT %s""",
                params,
            )
            rows = cur.fetchall()
        return [self._row_to_journal(r) for r in rows]

    def delete_journal(
        self,
        *,
        actions: Sequence[str],
        before: datetime,
        limit: int,
        dry_run: bool = False,
    ) -> int:
        if not actions or limit < 1:
            return 0
        params = (self._ns, before, list(actions), limit)
        subquery = """
            SELECT namespace, id FROM journal
            WHERE namespace = %s AND timestamp < %s AND action = ANY(%s)
            ORDER BY timestamp ASC
            LIMIT %s
        """
        with self._cursor() as cur:
            if dry_run:
                cur.execute(f"SELECT COUNT(*) AS n FROM ({subquery}) sub", params)
                row = cur.fetchone()
                return int(row["n"]) if row else 0
            cur.execute(
                f"DELETE FROM journal WHERE (namespace, id) IN ({subquery})",
                params,
            )
            deleted = int(cur.rowcount)
        return deleted

    def _meta_key(self, key: str) -> str:
        return f"{self._ns}:{key}"

    def get_meta(self, key: str) -> str | None:
        with self._cursor() as cur:
            cur.execute("SELECT value FROM meta WHERE key = %s", (self._meta_key(key),))
            row = cur.fetchone()
        return str(row["value"]) if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO meta (key, value) VALUES (%s, %s)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                (self._meta_key(key), value),
            )

    # ------------------------------------------------------------------
    # M5 — Episodes (L2.5 diary layer)
    # ------------------------------------------------------------------

    def save_episode(self, episode: Episode) -> None:
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO episodes
                    (namespace, id, raw_event_ids, occurred_at, summary, verbatim_quote,
                     quote_event_id, emotion, intensity, people, topics,
                     extractor_version, session_id, digest_ids, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    self._ns,
                    episode.id,
                    Jsonb(episode.raw_event_ids),
                    as_utc(episode.occurred_at),
                    episode.summary,
                    episode.verbatim_quote,
                    episode.quote_event_id,
                    episode.emotion,
                    int(episode.intensity),
                    Jsonb(episode.people),
                    Jsonb(episode.topics),
                    episode.extractor_version,
                    episode.session_id,
                    Jsonb(episode.digest_ids),
                    as_utc(episode.created_at),
                ),
            )

    def get_episode(self, episode_id: str) -> Episode | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM episodes WHERE namespace = %s AND id = %s",
                (self._ns, episode_id),
            )
            row = cur.fetchone()
        return self._row_to_episode(row) if row else None

    def list_episodes(
        self,
        *,
        session_id: str | None = None,
        emotion: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[Episode]:
        conditions: list[str] = ["namespace = %s"]
        params: list[Any] = [self._ns]
        if session_id is not None:
            conditions.append("session_id = %s")
            params.append(session_id)
        if emotion is not None:
            conditions.append("emotion = %s")
            params.append(emotion)
        if after is not None:
            conditions.append("occurred_at >= %s")
            params.append(as_utc(after))
        if before is not None:
            conditions.append("occurred_at < %s")
            params.append(as_utc(before))

        where = f"WHERE {' AND '.join(conditions)}"
        params.append(limit)

        with self._cursor() as cur:
            cur.execute(
                f"""SELECT * FROM episodes
                    {where}
                    ORDER BY occurred_at DESC
                    LIMIT %s""",
                params,
            )
            rows = cur.fetchall()
        return [self._row_to_episode(r) for r in rows]

    def search_episodes(self, query: str, *, limit: int = 10) -> list[Episode]:
        """FTS over summary + verbatim_quote + people + topics."""
        with self._cursor() as cur:
            cur.execute(
                """SELECT * FROM episodes
                    WHERE namespace = %s
                      AND fts_tsv @@ plainto_tsquery('simple', %s)
                    ORDER BY ts_rank(fts_tsv, plainto_tsquery('simple', %s)) DESC
                    LIMIT %s""",
                (self._ns, query, query, limit),
            )
            rows = cur.fetchall()
        return [self._row_to_episode(r) for r in rows]

    def list_episodes_in_range(
        self,
        *,
        start: datetime,
        end: datetime,
        limit: int = 500,
    ) -> list[Episode]:
        """List episodes whose ``occurred_at`` falls in ``[start, end)``, ASC."""
        with self._cursor() as cur:
            cur.execute(
                """SELECT * FROM episodes
                    WHERE namespace = %s AND occurred_at >= %s AND occurred_at < %s
                    ORDER BY occurred_at ASC
                    LIMIT %s""",
                (self._ns, as_utc(start), as_utc(end), limit),
            )
            rows = cur.fetchall()
        return [self._row_to_episode(r) for r in rows]

    # ------------------------------------------------------------------
    # M5 — Digests (weekly/monthly aggregates over episodes)
    # ------------------------------------------------------------------

    def upsert_digest(self, digest: DigestRecord) -> None:
        """Insert or replace a digest row keyed by ``(period_kind, period_key)``.

        On conflict the original ``id`` / ``created_at`` are preserved
        (matching the SQLite backend) while the aggregated fields are
        overwritten.
        """
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO digests
                    (namespace, id, period_kind, period_key, period_start, period_end,
                     markdown, episode_ids, llm_version, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (namespace, period_kind, period_key) DO UPDATE SET
                        period_start = EXCLUDED.period_start,
                        period_end = EXCLUDED.period_end,
                        markdown = EXCLUDED.markdown,
                        episode_ids = EXCLUDED.episode_ids,
                        llm_version = EXCLUDED.llm_version,
                        updated_at = EXCLUDED.updated_at""",
                (
                    self._ns,
                    digest.id,
                    digest.period_kind,
                    digest.period_key,
                    digest.period_start,
                    digest.period_end,
                    digest.markdown,
                    Jsonb(digest.episode_ids),
                    digest.llm_version,
                    digest.created_at,
                    digest.updated_at,
                ),
            )

    def get_digest(self, period_kind: DigestPeriod, period_key: str) -> DigestRecord | None:
        with self._cursor() as cur:
            cur.execute(
                """SELECT * FROM digests
                    WHERE namespace = %s AND period_kind = %s AND period_key = %s""",
                (self._ns, period_kind, period_key),
            )
            row = cur.fetchone()
        return self._row_to_digest(row) if row else None

    def list_digests(
        self,
        *,
        period_kind: DigestPeriod | None = None,
        limit: int = 50,
    ) -> list[DigestRecord]:
        conditions: list[str] = ["namespace = %s"]
        params: list[Any] = [self._ns]
        if period_kind is not None:
            conditions.append("period_kind = %s")
            params.append(period_kind)
        where = f"WHERE {' AND '.join(conditions)}"
        params.append(limit)
        with self._cursor() as cur:
            cur.execute(
                f"""SELECT * FROM digests
                    {where}
                    ORDER BY period_start DESC
                    LIMIT %s""",
                params,
            )
            rows = cur.fetchall()
        return [self._row_to_digest(r) for r in rows]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_node(row: dict[str, Any]) -> MemoryNode:
        raw_metadata = row.get("metadata")
        if raw_metadata is None:
            metadata: dict[str, Any] = {}
        elif isinstance(raw_metadata, str):
            metadata = json.loads(raw_metadata)
        else:
            metadata = dict(raw_metadata)
        atom_id = str(row["atom_id"]) if row.get("atom_id") else None
        atom_content = row.get("atom_content")
        return MemoryNode(
            id=str(row["id"]),
            parent_id=str(row["parent_id"]) if row["parent_id"] else None,
            level=row["level"],
            content=atom_content if atom_id is not None and atom_content is not None else row["content"],
            topic=row["topic"],
            conversation_id=str(row["conversation_id"]) if row["conversation_id"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=metadata,
            atom_id=atom_id,
        )

    @staticmethod
    def _row_to_raw(row: dict[str, Any]) -> RawEvent:
        raw_payload = row.get("payload")
        if raw_payload is None:
            payload: dict[str, Any] = {}
        elif isinstance(raw_payload, str):
            payload = json.loads(raw_payload)
        else:
            payload = dict(raw_payload)
        return RawEvent(
            id=str(row["id"]),
            host=row["host"],
            session_id=str(row["session_id"]) if row["session_id"] else None,
            thread_id=str(row["thread_id"]) if row["thread_id"] else None,
            user=row["user"],
            timestamp=row["timestamp"],
            event_type=row["event_type"],
            content=row["content"],
            payload=payload,
        )

    @staticmethod
    def _coerce_jsonb(value: Any) -> Any:
        """Normalize a psycopg JSONB value to a Python object.

        psycopg returns JSONB columns either as already-decoded objects
        or as JSON strings depending on adapter setup. Normalise both.
        """
        if value is None:
            return None
        if isinstance(value, str):
            return json.loads(value)
        return value

    @staticmethod
    def _row_to_candidate(row: dict[str, Any]) -> Candidate:
        return Candidate(
            id=str(row["id"]),
            raw_event_ids=PostgresMemoryBackend._coerce_jsonb(row["raw_event_ids"]) or [],
            candidate_type=row["candidate_type"],
            status=row["status"],
            title=row["title"],
            assertion=row["assertion"],
            verbatim_quote=row["verbatim_quote"],
            quote_event_id=str(row["quote_event_id"]),
            subject_name=row["subject_name"],
            subject_entity_type=row["subject_entity_type"],
            target_entity_id=str(row["target_entity_id"]) if row["target_entity_id"] else None,
            confidence=row["confidence"],
            importance=row["importance"],
            recommended_action=row["recommended_action"],
            promotion_reason=row["promotion_reason"],
            extractor_version=row["extractor_version"],
            created_at=row["created_at"],
            decided_at=row.get("decided_at"),
            decided_by=row.get("decided_by"),
            session_id=row.get("session_id"),
            payload=PostgresMemoryBackend._coerce_jsonb(row.get("payload")) or {},
        )

    @staticmethod
    def _row_to_atom(row: dict[str, Any]) -> AtomCard:
        return AtomCard(
            id=str(row["id"]),
            entity_id=str(row["entity_id"]),
            candidate_id=str(row["candidate_id"]),
            raw_event_ids=PostgresMemoryBackend._coerce_jsonb(row["raw_event_ids"]) or [],
            assertion=row["assertion"],
            verbatim_quote=row["verbatim_quote"],
            quote_event_id=str(row["quote_event_id"]),
            search_terms=PostgresMemoryBackend._coerce_jsonb(row["search_terms"]) or [],
            occurred_at=row["occurred_at"],
            confidence=row["confidence"],
            importance=row["importance"],
            superseded_by=str(row["superseded_by"]) if row.get("superseded_by") else None,
            deprecated_at=row.get("deprecated_at"),
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_entity(row: dict[str, Any]) -> Entity:
        return Entity(
            id=str(row["id"]),
            entity_type=row["entity_type"],
            canonical_name=row["canonical_name"],
            aliases=PostgresMemoryBackend._coerce_jsonb(row.get("aliases")) or [],
            atom_count=int(row["atom_count"]),
            last_promoted_at=row.get("last_promoted_at"),
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_entity_page(row: dict[str, Any]) -> EntityPage:
        return EntityPage(
            id=str(row["id"]),
            entity_id=str(row["entity_id"]),
            summary_markdown=row.get("summary_markdown") or "",
            headline=row.get("headline") or "",
            topics=PostgresMemoryBackend._coerce_jsonb(row.get("topics")) or [],
            dirty=bool(row["dirty"]),
            regen_attempt_count=int(row.get("regen_attempt_count") or 0),
            summary_version=int(row.get("summary_version") or 0),
            last_regen_at=row.get("last_regen_at"),
            last_user_edit_at=row.get("last_user_edit_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_alias(row: dict[str, Any]) -> Alias:
        return Alias(
            alias=row["alias"],
            entity_id=str(row["entity_id"]),
            entity_type=row["entity_type"],
            created_by=row["created_by"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_journal(row: dict[str, Any]) -> JournalEntry:
        return JournalEntry(
            id=str(row["id"]),
            timestamp=row["timestamp"],
            action=row["action"],
            actor=row["actor"],
            target_entity_id=str(row["target_entity_id"]) if row.get("target_entity_id") else None,
            target_atom_id=str(row["target_atom_id"]) if row.get("target_atom_id") else None,
            target_candidate_id=str(row["target_candidate_id"]) if row.get("target_candidate_id") else None,
            before=PostgresMemoryBackend._coerce_jsonb(row.get("before")),
            after=PostgresMemoryBackend._coerce_jsonb(row.get("after")),
            note=row.get("note") or "",
        )

    @staticmethod
    def _row_to_episode(row: dict[str, Any]) -> Episode:
        return Episode(
            id=str(row["id"]),
            raw_event_ids=PostgresMemoryBackend._coerce_jsonb(row.get("raw_event_ids")) or [],
            occurred_at=as_utc(row["occurred_at"]),
            summary=row["summary"],
            verbatim_quote=row["verbatim_quote"],
            quote_event_id=str(row["quote_event_id"]),
            emotion=row["emotion"],
            intensity=int(row["intensity"]),
            people=PostgresMemoryBackend._coerce_jsonb(row.get("people")) or [],
            topics=PostgresMemoryBackend._coerce_jsonb(row.get("topics")) or [],
            extractor_version=row["extractor_version"],
            session_id=str(row["session_id"]) if row.get("session_id") else None,
            digest_ids=PostgresMemoryBackend._coerce_jsonb(row.get("digest_ids")) or [],
            created_at=as_utc(row["created_at"]),
        )

    @staticmethod
    def _row_to_digest(row: dict[str, Any]) -> DigestRecord:
        return DigestRecord(
            id=str(row["id"]),
            period_kind=row["period_kind"],
            period_key=row["period_key"],
            period_start=row["period_start"],
            period_end=row["period_end"],
            markdown=row.get("markdown") or "",
            episode_ids=PostgresMemoryBackend._coerce_jsonb(row.get("episode_ids")) or [],
            llm_version=row["llm_version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
