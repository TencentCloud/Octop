"""SQLite-based memory backend with FTS5 full-text search."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any, Concatenate

from octop_memory.domain.datetime import as_utc, parse_datetime_utc
from octop_memory.storage.backends import _UNSET, _Unset
from octop_memory.storage.backends.fts_text import (
    FTS_TEXT_VERSION,
    fts_match_phrase,
    register_fts_functions,
)
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

# Stamped into {ns}_meta on every open. External tools (portable doctor,
# portable list-sources) read it to distinguish a healthy octop-memory
# store from a foreign/corrupt SQLite file. Bump when the DDL changes shape.
SCHEMA_VERSION = "1"
SQLITE_BUSY_TIMEOUT_MS = 30_000
"""Wait this long on a locked connection before raising ``database is locked``.

VACUUM still holds an exclusive lock for the whole rewrite; hosts should
disable writes for that agent while compacting. This only covers short
overlaps (prune commits, WAL checkpoint).
"""


def locked_sqlite_operation[**P, R](
    method: Callable[Concatenate[SqliteMemoryBackend, P], R],
) -> Callable[Concatenate[SqliteMemoryBackend, P], R]:
    """Serialize a full SQL operation, including its fetch and commit."""

    @wraps(method)
    def guarded(self: SqliteMemoryBackend, /, *args: P.args, **kwargs: P.kwargs) -> R:
        with self._conn_lock:
            if self._closed:
                raise sqlite3.ProgrammingError("Cannot operate on a closed database.")
            try:
                return method(self, *args, **kwargs)
            except Exception:
                # Failed standalone writes must not enlist the next caller
                # in an abandoned implicit transaction. Explicit transactions
                # retain ownership of their rollback boundary.
                if not self._in_transaction and self._conn.in_transaction:
                    self._conn.rollback()
                raise

    return guarded


class SqliteMemoryBackend:
    """Memory backend using SQLite + FTS5.

    Multi-agent isolation via table-name prefix (namespace).
    Default database path: ``~/.octop-memory/session.sqlite``.

    One connection per backend, serialized for a full operation/transaction.
    Worker pools do not multiply persistent handles by agent count. Each
    backend has its own lock; checkpointing uses a separate connection.
    ``close()`` waits for active operations and does not reopen.
    """

    def __init__(
        self,
        namespace: str,
        db_path: str | Path = "~/.octop-memory/session.sqlite",
    ) -> None:
        self._ns = re.sub(r"[^a-z0-9_]", "_", namespace.lower())
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._closed = False
        self._conn_lock = threading.RLock()
        self._in_transaction = False
        self._connection = self._new_connection()
        try:
            self._init_schema()
        except Exception:
            self.close()
            raise

    def _new_connection(self) -> sqlite3.Connection:
        # The backend lock covers execute/fetch/commit and explicit transactions.
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            # Must run before CREATE TABLE on a new file (ADR-027). On a
            # pre-existing NONE database this pragma is stored but does not
            # take effect until a full VACUUM (compact_vacuum).
            conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            register_fts_functions(conn)
            return conn
        except Exception:
            conn.close()
            raise

    @property
    def _conn(self) -> sqlite3.Connection:
        """Internal handle. SQL callers must hold ``_conn_lock`` for the full operation."""
        if self._closed:
            raise sqlite3.ProgrammingError("Cannot operate on a closed database.")
        return self._connection

    def close(self) -> None:
        """Wait for active SQL/transactions, then close without reopening."""
        with self._conn_lock:
            self._closed = True
            self._connection.close()

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Wrap multiple writes in a single atomic SQLite transaction.

        Re-entrant safe on the *current thread*: nested calls are no-ops
        (the outer transaction owns the commit/rollback boundary).
        """
        with self._conn_lock:
            if self._in_transaction:
                yield
                return
            self._conn.execute("BEGIN")
            self._in_transaction = True
            committed = False
            try:
                yield
                self._conn.execute("COMMIT")
                committed = True
            finally:
                try:
                    if not committed:
                        self._conn.execute("ROLLBACK")
                finally:
                    self._in_transaction = False

    def _commit(self) -> None:
        """Commit only when not inside an explicit transaction block.

        Individual ``save_*`` methods call this instead of
        ``self._commit()`` directly so that callers wrapping multiple
        writes in ``transaction()`` get a single atomic commit.
        """
        if not self._in_transaction:
            self._conn.commit()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        ns = self._ns
        self._conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS {ns}_memory_nodes (
                id TEXT PRIMARY KEY,
                parent_id TEXT,
                level TEXT NOT NULL CHECK (level IN ('root', 'branch', 'leaf')),
                atom_id TEXT UNIQUE,
                content TEXT NOT NULL,
                topic TEXT,
                conversation_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{{}}'
            );
            CREATE INDEX IF NOT EXISTS {ns}_memory_nodes_parent
                ON {ns}_memory_nodes(parent_id);
            CREATE INDEX IF NOT EXISTS {ns}_memory_nodes_level
                ON {ns}_memory_nodes(level);
            CREATE TABLE IF NOT EXISTS {ns}_raw_events (
                id TEXT PRIMARY KEY,
                host TEXT NOT NULL,
                session_id TEXT,
                thread_id TEXT,
                user TEXT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                content TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{{}}'
            );
            CREATE INDEX IF NOT EXISTS {ns}_raw_events_time
                ON {ns}_raw_events(timestamp);
            CREATE INDEX IF NOT EXISTS {ns}_raw_events_session
                ON {ns}_raw_events(session_id);
            CREATE INDEX IF NOT EXISTS {ns}_raw_events_thread
                ON {ns}_raw_events(thread_id);
            CREATE INDEX IF NOT EXISTS {ns}_raw_events_host
                ON {ns}_raw_events(host);
            CREATE INDEX IF NOT EXISTS {ns}_raw_events_type
                ON {ns}_raw_events(event_type);

            -- M2: L1 Candidates -----------------------------------------
            CREATE TABLE IF NOT EXISTS {ns}_candidates (
                id TEXT PRIMARY KEY,
                raw_event_ids TEXT NOT NULL,
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
                created_at TEXT NOT NULL,
                decided_at TEXT,
                decided_by TEXT,
                session_id TEXT,
                payload TEXT NOT NULL DEFAULT '{{}}'
            );
            CREATE INDEX IF NOT EXISTS {ns}_candidates_status
                ON {ns}_candidates(status);
            CREATE INDEX IF NOT EXISTS {ns}_candidates_session
                ON {ns}_candidates(session_id);
            CREATE INDEX IF NOT EXISTS {ns}_candidates_target_entity
                ON {ns}_candidates(target_entity_id);
            CREATE INDEX IF NOT EXISTS {ns}_candidates_created_at
                ON {ns}_candidates(created_at);

            -- M2: L2 Atoms ---------------------------------------------
            CREATE TABLE IF NOT EXISTS {ns}_atoms (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                raw_event_ids TEXT NOT NULL,
                assertion TEXT NOT NULL,
                verbatim_quote TEXT NOT NULL,
                quote_event_id TEXT NOT NULL,
                search_terms TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                confidence TEXT NOT NULL,
                importance TEXT NOT NULL,
                superseded_by TEXT,
                deprecated_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS {ns}_atoms_entity
                ON {ns}_atoms(entity_id);
            CREATE INDEX IF NOT EXISTS {ns}_atoms_importance
                ON {ns}_atoms(importance);
            CREATE INDEX IF NOT EXISTS {ns}_atoms_created_at
                ON {ns}_atoms(created_at);
            CREATE INDEX IF NOT EXISTS {ns}_atoms_superseded
                ON {ns}_atoms(superseded_by);

            -- M2: L3 Entities (minimal — no summary; D28) --------------
            CREATE TABLE IF NOT EXISTS {ns}_entities (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                canonical_name TEXT NOT NULL,
                aliases TEXT NOT NULL DEFAULT '[]',
                atom_count INTEGER NOT NULL DEFAULT 0,
                last_promoted_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS {ns}_entities_type
                ON {ns}_entities(entity_type);
            CREATE INDEX IF NOT EXISTS {ns}_entities_name
                ON {ns}_entities(canonical_name COLLATE NOCASE);

            -- M2: Aliases (string-normalized lookup) -------------------
            CREATE TABLE IF NOT EXISTS {ns}_aliases (
                alias TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (alias, entity_id)
            );
            CREATE INDEX IF NOT EXISTS {ns}_aliases_alias
                ON {ns}_aliases(alias);
            CREATE INDEX IF NOT EXISTS {ns}_aliases_entity
                ON {ns}_aliases(entity_id);

            -- M3: L3 Entity Pages (long-form summary; D32-D37) ---------
            CREATE TABLE IF NOT EXISTS {ns}_entity_pages (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL UNIQUE,
                summary_markdown TEXT NOT NULL DEFAULT '',
                headline TEXT NOT NULL DEFAULT '',
                topics TEXT NOT NULL DEFAULT '[]',
                dirty INTEGER NOT NULL DEFAULT 1,
                regen_attempt_count INTEGER NOT NULL DEFAULT 0,
                summary_version INTEGER NOT NULL DEFAULT 0,
                last_regen_at TEXT,
                last_user_edit_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS {ns}_entity_pages_dirty
                ON {ns}_entity_pages(dirty);
            CREATE INDEX IF NOT EXISTS {ns}_entity_pages_updated
                ON {ns}_entity_pages(updated_at);
            CREATE INDEX IF NOT EXISTS {ns}_entity_pages_last_regen
                ON {ns}_entity_pages(last_regen_at);

            -- M4: thread active-entity LRU stack (D41a + D41b) ----------
            CREATE TABLE IF NOT EXISTS {ns}_thread_active_entities (
                thread_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'recall_hit',
                PRIMARY KEY (thread_id, entity_id)
            );
            CREATE INDEX IF NOT EXISTS {ns}_thread_active_entities_seen
                ON {ns}_thread_active_entities(thread_id, last_seen_at DESC);

            -- M5: L2.5 Episodes (situational/emotional diary) ---------
            CREATE TABLE IF NOT EXISTS {ns}_episodes (
                id TEXT PRIMARY KEY,
                raw_event_ids TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                summary TEXT NOT NULL,
                verbatim_quote TEXT NOT NULL,
                quote_event_id TEXT NOT NULL,
                emotion TEXT NOT NULL DEFAULT 'neutral',
                intensity INTEGER NOT NULL DEFAULT 1,
                people TEXT NOT NULL DEFAULT '[]',
                topics TEXT NOT NULL DEFAULT '[]',
                extractor_version TEXT NOT NULL,
                session_id TEXT,
                digest_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS {ns}_episodes_occurred
                ON {ns}_episodes(occurred_at);
            CREATE INDEX IF NOT EXISTS {ns}_episodes_session
                ON {ns}_episodes(session_id);
            CREATE INDEX IF NOT EXISTS {ns}_episodes_emotion
                ON {ns}_episodes(emotion);

            -- M5: Weekly/monthly digests of episodes -------------------
            CREATE TABLE IF NOT EXISTS {ns}_digests (
                id TEXT PRIMARY KEY,
                period_kind TEXT NOT NULL,
                period_key TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                markdown TEXT NOT NULL,
                episode_ids TEXT NOT NULL DEFAULT '[]',
                llm_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (period_kind, period_key)
            );
            CREATE INDEX IF NOT EXISTS {ns}_digests_period
                ON {ns}_digests(period_kind, period_key);
            CREATE INDEX IF NOT EXISTS {ns}_digests_start
                ON {ns}_digests(period_start);

            -- M2: L4 Journal (append-only audit log) -------------------
            CREATE TABLE IF NOT EXISTS {ns}_journal (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                target_entity_id TEXT,
                target_atom_id TEXT,
                target_candidate_id TEXT,
                before TEXT,
                after TEXT,
                note TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS {ns}_journal_time
                ON {ns}_journal(timestamp);
            CREATE INDEX IF NOT EXISTS {ns}_journal_action
                ON {ns}_journal(action);
            -- target_* start as plain (non-partial) indexes here — SQLite
            -- happily leaves a pre-existing index alone under IF NOT
            -- EXISTS, so widening them to WHERE ... IS NOT NULL belongs
            -- in _migrate_journal_target_indexes_to_partial() (runs for
            -- both fresh and legacy databases via _migrate_schema()) and
            -- not here. See RISK-026 / ADR-024.
            CREATE INDEX IF NOT EXISTS {ns}_journal_target_entity
                ON {ns}_journal(target_entity_id);
            CREATE INDEX IF NOT EXISTS {ns}_journal_target_atom
                ON {ns}_journal(target_atom_id);
            CREATE INDEX IF NOT EXISTS {ns}_journal_target_candidate
                ON {ns}_journal(target_candidate_id);
        """)

        # FTS5 tables (CREATE VIRTUAL TABLE IF NOT EXISTS is supported)
        self._conn.executescript(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {ns}_memory_fts USING fts5(
                content,
                topic,
                content='{ns}_memory_nodes',
                content_rowid='rowid',
                tokenize='unicode61'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS {ns}_raw_events_fts USING fts5(
                content,
                content='{ns}_raw_events',
                content_rowid='rowid',
                tokenize='unicode61'
            );

            -- M2 FTS tables -------------------------------------------
            CREATE VIRTUAL TABLE IF NOT EXISTS {ns}_candidates_fts USING fts5(
                title,
                assertion,
                verbatim_quote,
                content='{ns}_candidates',
                content_rowid='rowid',
                tokenize='unicode61'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS {ns}_atoms_fts USING fts5(
                assertion,
                verbatim_quote,
                search_terms,
                content='{ns}_atoms',
                content_rowid='rowid',
                tokenize='unicode61'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS {ns}_episodes_fts USING fts5(
                summary,
                verbatim_quote,
                people,
                topics,
                content='{ns}_episodes',
                content_rowid='rowid',
                tokenize='unicode61'
            );
        """)

        self._create_fts_triggers()
        self._commit()
        self._migrate_schema()

    # FTS sync specs shared by trigger creation and the v2 rebuild
    # migration. ``metadata`` is intentionally excluded from FTS — it
    # stores reference fields for upper layers, not searchable text.
    # Every value expression is wrapped in hm_cjk_seg() so CJK text is
    # indexed per-character (see storage/backends/fts_text.py).
    _FTS_SYNC_SPECS: tuple[tuple[str, str, str, str, tuple[tuple[str, str], ...], bool], ...] = (
        # (trigger_prefix, base_suffix, fts_suffix, rowid_expr, columns, with_update_trigger)
        (
            "memory",
            "memory_nodes",
            "memory_fts",
            "rowid",
            (("content", "{row}.content"), ("topic", "COALESCE({row}.topic, '')")),
            True,
        ),
        ("raw_events", "raw_events", "raw_events_fts", "rowid", (("content", "{row}.content"),), False),
        (
            "candidates",
            "candidates",
            "candidates_fts",
            "rowid",
            (
                ("title", "{row}.title"),
                ("assertion", "{row}.assertion"),
                ("verbatim_quote", "{row}.verbatim_quote"),
            ),
            True,
        ),
        # Atoms are append-only with deprecation; search_terms can change
        # as the worker re-indexes, so atoms keep an UPDATE trigger.
        (
            "atoms",
            "atoms",
            "atoms_fts",
            "rowid",
            (
                ("assertion", "{row}.assertion"),
                ("verbatim_quote", "{row}.verbatim_quote"),
                ("search_terms", "{row}.search_terms"),
            ),
            True,
        ),
        # Episodes (M5) — user diary; FTS over summary + verbatim + tags.
        (
            "episodes",
            "episodes",
            "episodes_fts",
            "rowid",
            (
                ("summary", "{row}.summary"),
                ("verbatim_quote", "{row}.verbatim_quote"),
                ("people", "{row}.people"),
                ("topics", "{row}.topics"),
            ),
            True,
        ),
    )

    def _create_fts_triggers(self) -> None:
        """(Re)create the FTS-sync triggers with CJK-segmented bodies."""
        ns = self._ns
        statements: list[str] = []
        for prefix, base_suffix, fts_suffix, rowid_expr, columns, with_update in self._FTS_SYNC_SPECS:
            base = f"{ns}_{base_suffix}"
            fts = f"{ns}_{fts_suffix}"
            col_list = ", ".join(name for name, _ in columns)
            new_vals = ", ".join(f"hm_cjk_seg({expr.format(row='new')})" for _, expr in columns)
            old_vals = ", ".join(f"hm_cjk_seg({expr.format(row='old')})" for _, expr in columns)
            statements.append(
                f"CREATE TRIGGER IF NOT EXISTS {ns}_{prefix}_ai "
                f"AFTER INSERT ON {base} BEGIN "
                f"INSERT INTO {fts}(rowid, {col_list}) VALUES (new.{rowid_expr}, {new_vals}); "
                f"END;"
            )
            statements.append(
                f"CREATE TRIGGER IF NOT EXISTS {ns}_{prefix}_ad "
                f"AFTER DELETE ON {base} BEGIN "
                f"INSERT INTO {fts}({fts}, rowid, {col_list}) "
                f"VALUES ('delete', old.{rowid_expr}, {old_vals}); "
                f"END;"
            )
            if with_update:
                statements.append(
                    f"CREATE TRIGGER IF NOT EXISTS {ns}_{prefix}_au "
                    f"AFTER UPDATE ON {base} BEGIN "
                    f"INSERT INTO {fts}({fts}, rowid, {col_list}) "
                    f"VALUES ('delete', old.{rowid_expr}, {old_vals}); "
                    f"INSERT INTO {fts}(rowid, {col_list}) VALUES (new.{rowid_expr}, {new_vals}); "
                    f"END;"
                )
        self._conn.executescript("\n".join(statements))

    def _migrate_fts_text_version(self) -> None:
        """Rebuild FTS triggers + index when the segmentation version changes.

        Pre-v2 databases indexed raw text with unicode61, which collapses
        a contiguous Han run into a single token — Chinese queries matched
        almost nothing. The rebuild drops the old triggers (CREATE TRIGGER
        IF NOT EXISTS would keep them), recreates them with hm_cjk_seg()
        bodies, and re-derives every FTS row from its base table.
        """
        ns = self._ns
        self._conn.execute(f"CREATE TABLE IF NOT EXISTS {ns}_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        row = self._conn.execute(f"SELECT value FROM {ns}_meta WHERE key = 'fts_text_version'").fetchone()
        if row is not None and row[0] == FTS_TEXT_VERSION:
            return

        for prefix, base_suffix, _fts, _rowid, _cols, _wu in self._FTS_SYNC_SPECS:
            # Drop both naming schemes: _init_schema uses the trigger
            # prefix ({ns}_memory_ai), operations/migration/rename.py historically
            # used the base-table suffix ({ns}_memory_nodes_ai). Leaving
            # either behind would double-insert into FTS.
            for name in {prefix, base_suffix}:
                for suffix in ("ai", "ad", "au"):
                    self._conn.execute(f"DROP TRIGGER IF EXISTS {ns}_{name}_{suffix}")
        self._create_fts_triggers()

        for _prefix, base_suffix, fts_suffix, rowid_expr, columns, _wu in self._FTS_SYNC_SPECS:
            base = f"{ns}_{base_suffix}"
            fts = f"{ns}_{fts_suffix}"
            col_list = ", ".join(name for name, _ in columns)
            col_select = ", ".join(f"hm_cjk_seg({expr.format(row=base)})" for _, expr in columns)
            self._conn.execute(f"INSERT INTO {fts}({fts}) VALUES ('delete-all')")
            self._conn.execute(
                f"INSERT INTO {fts}(rowid, {col_list}) SELECT {base}.{rowid_expr}, {col_select} FROM {base}"
            )

        self._conn.execute(
            f"INSERT INTO {ns}_meta (key, value) VALUES ('fts_text_version', ?) "
            f"ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (FTS_TEXT_VERSION,),
        )
        self._commit()

    def _migrate_schema(self) -> None:
        """Apply incremental schema migrations for existing databases.

        ``CREATE TABLE IF NOT EXISTS`` is a no-op on pre-existing tables,
        so new columns must be added via ``ALTER TABLE``. SQLite doesn't
        support ``ADD COLUMN IF NOT EXISTS``, so we inspect the column
        list first.
        """
        ns = self._ns
        # M0: add metadata column to memory_nodes for existing databases
        nodes_table = f"{ns}_memory_nodes"
        node_cols = {row[1] for row in self._conn.execute(f"PRAGMA table_info({nodes_table})").fetchall()}
        if "metadata" not in node_cols:
            self._conn.execute(f"ALTER TABLE {nodes_table} ADD COLUMN metadata TEXT NOT NULL DEFAULT '{{}}'")
            self._commit()
        if "atom_id" not in node_cols:
            self._conn.execute(f"ALTER TABLE {nodes_table} ADD COLUMN atom_id TEXT")
            self._commit()
        self._conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {ns}_memory_nodes_atom ON {nodes_table}(atom_id)")
        self._commit()

        # CJK FTS segmentation (fts_text v2): rebuild triggers + index
        # for databases created before the segmentation fix.
        self._migrate_fts_text_version()

        # RISK-026 / ADR-024: journal target_* indexes → partial.
        self._migrate_journal_target_indexes_to_partial()

        # Stamp the schema version (the meta table exists by now). Until
        # 0.9.2 nothing ever wrote this key, so tools that read it (portable
        # doctor / list-sources) must treat a missing row as "older store",
        # not corruption.
        self._conn.execute(
            f"INSERT INTO {ns}_meta (key, value) VALUES ('schema_version', ?) "
            f"ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SCHEMA_VERSION,),
        )
        self._commit()

    _JOURNAL_PARTIAL_TARGET_INDEXES: tuple[tuple[str, str], ...] = (
        ("target_entity", "target_entity_id"),
        ("target_atom", "target_atom_id"),
        ("target_candidate", "target_candidate_id"),
    )
    """(index name suffix, column) pairs for the journal target_* indexes.

    Historical ``extract_run`` rows (the table's largest leftover source)
    never set any of these three columns (new extracts write meta instead),
    so a plain index spends space on leaf entries for rows no equality
    filter (``WHERE target_atom_id = ?``) could ever match. Only
    business-action rows (promote/reject/deprecate/...) populate them.
    """

    def _migrate_journal_target_indexes_to_partial(self) -> None:
        """Narrow the journal target_* indexes to ``WHERE col IS NOT NULL``.

        Query semantics are unchanged — a partial index still answers
        ``WHERE target_atom_id = ?`` correctly, it just never had a NULL
        row to skip over in the first place. Idempotent via
        ``sqlite_master`` introspection rather than a stamped version:
        the common case (already migrated) costs one cheap ``SELECT``
        per index and no ``DROP``/``CREATE``; the ``DROP INDEX`` +
        ``CREATE INDEX`` (an O(rows) rebuild) only runs for a database
        that still has the pre-migration plain index.
        """
        ns = self._ns
        for suffix, column in self._JOURNAL_PARTIAL_TARGET_INDEXES:
            index_name = f"{ns}_journal_{suffix}"
            row = self._conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
                (index_name,),
            ).fetchone()
            existing_sql = row[0] if row and row[0] else ""
            if "WHERE" in existing_sql.upper():
                continue  # already partial
            self._conn.execute(f"DROP INDEX IF EXISTS {index_name}")
            self._conn.execute(f"CREATE INDEX {index_name} ON {ns}_journal({column}) WHERE {column} IS NOT NULL")
        self._commit()

    # ------------------------------------------------------------------
    # Memory tree
    # ------------------------------------------------------------------

    @locked_sqlite_operation
    def save_node(self, node: MemoryNode) -> None:
        """Insert a new memory node.

        **Strict insert** (no INSERT OR REPLACE): re-inserting the same
        ``id`` raises ``sqlite3.IntegrityError``. Updates must go through
        :meth:`update_node` explicitly. This is defensive — silent
        overwrite would let buggy callers lose data without any signal.
        """
        if node.level == "leaf" and node.atom_id is None:
            raise ValueError("leaf nodes must reference an AtomCard via atom_id")
        if node.level != "leaf" and node.atom_id is not None:
            raise ValueError("root and branch nodes cannot reference an AtomCard")
        ns = self._ns
        stored_content = "" if node.level == "leaf" and node.atom_id is not None else node.content
        self._conn.execute(
            f"""INSERT INTO {ns}_memory_nodes
                (id, parent_id, level, atom_id, content, topic, conversation_id, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                node.id,
                node.parent_id,
                node.level,
                node.atom_id,
                stored_content,
                node.topic,
                node.conversation_id,
                node.created_at.isoformat(),
                node.updated_at.isoformat(),
                json.dumps(node.metadata, ensure_ascii=False),
            ),
        )
        self._commit()

    @locked_sqlite_operation
    def get_node(self, node_id: str) -> MemoryNode | None:
        """Fetch a single node by id, or ``None`` if not found."""
        ns = self._ns
        row = self._conn.execute(
            f"""SELECT n.*, a.assertion AS atom_content
                FROM {ns}_memory_nodes n
                LEFT JOIN {ns}_atoms a ON a.id = n.atom_id
                WHERE n.id = ?""",
            (node_id,),
        ).fetchone()
        return self._row_to_node(row) if row else None

    @locked_sqlite_operation
    def get_node_by_atom_id(self, atom_id: str) -> MemoryNode | None:
        """Fetch the leaf node that references ``atom_id``, or ``None``."""
        ns = self._ns
        row = self._conn.execute(
            f"""SELECT n.*, a.assertion AS atom_content
                FROM {ns}_memory_nodes n
                LEFT JOIN {ns}_atoms a ON a.id = n.atom_id
                WHERE n.atom_id = ?""",
            (atom_id,),
        ).fetchone()
        return self._row_to_node(row) if row else None

    @locked_sqlite_operation
    def get_children(self, parent_id: str | None) -> list[MemoryNode]:
        ns = self._ns
        if parent_id is None:
            rows = self._conn.execute(
                f"""SELECT n.*, a.assertion AS atom_content
                    FROM {ns}_memory_nodes n
                    LEFT JOIN {ns}_atoms a ON a.id = n.atom_id
                    WHERE n.parent_id IS NULL"""
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"""SELECT n.*, a.assertion AS atom_content
                    FROM {ns}_memory_nodes n
                    LEFT JOIN {ns}_atoms a ON a.id = n.atom_id
                    WHERE n.parent_id = ?""",
                (parent_id,),
            ).fetchall()
        return [self._row_to_node(r) for r in rows]

    @locked_sqlite_operation
    def update_node(
        self,
        node_id: str,
        *,
        content: str | None = None,
        topic: str | _Unset | None = _UNSET,
        metadata: dict[str, Any] | _Unset | None = _UNSET,
    ) -> bool:
        """Update one or more mutable fields of an existing node.

        ``parent_id`` and ``level`` are intentionally **not** mutable
        here: structural moves and tree validation are responsibilities
        of the service layer (``Memory``). Re-parenting also requires
        cycle detection, which is centralized in a future
        ``Memory.move()`` API.

        ``metadata`` semantics is **replace** (whole-dict overwrite),
        not patch-merge. Patch semantics, if needed, will be added as a
        separate API.

        Use the sentinel ``_UNSET`` to distinguish "do not touch" from
        "set to ``None`` / empty dict".

        Returns ``True`` if the node existed and was updated, else ``False``.
        """
        ns = self._ns
        sets: list[str] = []
        params: list[Any] = []
        if content is not None:
            sets.append("content = ?")
            params.append(content)
        if not isinstance(topic, _Unset):
            sets.append("topic = ?")
            params.append(topic)
        if not isinstance(metadata, _Unset):
            sets.append("metadata = ?")
            params.append(json.dumps(metadata or {}, ensure_ascii=False))

        if not sets:
            # Nothing to update; still verify existence for honest return value.
            row = self._conn.execute(f"SELECT 1 FROM {ns}_memory_nodes WHERE id = ?", (node_id,)).fetchone()
            return row is not None

        sets.append("updated_at = ?")
        params.append(datetime.now(UTC).isoformat())
        params.append(node_id)

        cur = self._conn.execute(
            f"UPDATE {ns}_memory_nodes SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        self._commit()
        return cur.rowcount > 0

    @locked_sqlite_operation
    def delete_node(self, node_id: str, *, cascade: bool = False) -> bool:
        """Delete a node by id.

        If ``cascade=False`` (default) and the node has children, raises
        ``ValueError``. If ``cascade=True``, recursively deletes the
        entire subtree rooted at ``node_id``.

        FTS index is kept in sync via ``{ns}_memory_ad`` trigger so
        deleted nodes never linger in search results.

        Returns ``True`` if at least one row was deleted, else ``False``.
        """
        ns = self._ns
        # Verify node exists.
        row = self._conn.execute(f"SELECT 1 FROM {ns}_memory_nodes WHERE id = ?", (node_id,)).fetchone()
        if row is None:
            return False

        if cascade:
            # Collect entire subtree (BFS) to delete in one shot.
            to_delete: list[str] = []
            frontier: list[str] = [node_id]
            while frontier:
                placeholders = ",".join("?" * len(frontier))
                child_rows = self._conn.execute(
                    f"SELECT id FROM {ns}_memory_nodes WHERE parent_id IN ({placeholders})",
                    frontier,
                ).fetchall()
                to_delete.extend(frontier)
                frontier = [r["id"] for r in child_rows]
            placeholders = ",".join("?" * len(to_delete))
            self._conn.execute(
                f"DELETE FROM {ns}_memory_nodes WHERE id IN ({placeholders})",
                to_delete,
            )
        else:
            child_count = self._conn.execute(
                f"SELECT COUNT(*) FROM {ns}_memory_nodes WHERE parent_id = ?",
                (node_id,),
            ).fetchone()[0]
            if child_count > 0:
                raise ValueError(f"Node {node_id!r} has {child_count} child(ren); pass cascade=True to delete subtree.")
            self._conn.execute(f"DELETE FROM {ns}_memory_nodes WHERE id = ?", (node_id,))
        self._commit()
        return True

    @locked_sqlite_operation
    def search_memories(self, query: str, limit: int = 5) -> list[MemoryNode]:
        ns = self._ns
        safe_query = fts_match_phrase(query)
        rows = self._conn.execute(
            f"""SELECT n.*, a.assertion AS atom_content
                FROM {ns}_atoms_fts f
                JOIN {ns}_atoms a ON f.rowid = a.rowid
                JOIN {ns}_memory_nodes n ON n.atom_id = a.id
                WHERE f.{ns}_atoms_fts MATCH ?
                  AND a.deprecated_at IS NULL
                ORDER BY rank
                LIMIT ?""",
            (safe_query, limit),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    @locked_sqlite_operation
    def get_tree(self) -> list[MemoryNode]:
        ns = self._ns
        rows = self._conn.execute(
            f"""SELECT n.*, a.assertion AS atom_content
                FROM {ns}_memory_nodes n
                LEFT JOIN {ns}_atoms a ON a.id = n.atom_id"""
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    # ------------------------------------------------------------------
    # L0 Raw events (M1)
    # ------------------------------------------------------------------

    @locked_sqlite_operation
    def save_raw(self, event: RawEvent) -> None:
        """Append a raw event. Strict insert; duplicate id → IntegrityError.

        RawEvent rows are immutable; corrections happen by inserting
        new events, never by mutating old ones.
        """
        ns = self._ns
        self._conn.execute(
            f"""INSERT INTO {ns}_raw_events
                (id, host, session_id, thread_id, user, timestamp,
                 event_type, content, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.id,
                event.host,
                event.session_id,
                event.thread_id,
                event.user,
                event.timestamp.isoformat(),
                event.event_type,
                event.content,
                json.dumps(event.payload, ensure_ascii=False),
            ),
        )
        self._commit()

    @locked_sqlite_operation
    def save_raw_batch(self, events: list[RawEvent]) -> None:
        """Append many raw events in a single transaction (1 fsync)."""
        if not events:
            return
        ns = self._ns
        rows = [
            (
                e.id,
                e.host,
                e.session_id,
                e.thread_id,
                e.user,
                e.timestamp.isoformat(),
                e.event_type,
                e.content,
                json.dumps(e.payload, ensure_ascii=False),
            )
            for e in events
        ]
        self._conn.executemany(
            f"""INSERT INTO {ns}_raw_events
                (id, host, session_id, thread_id, user, timestamp,
                 event_type, content, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self._commit()

    @locked_sqlite_operation
    def get_raw(self, event_id: str) -> RawEvent | None:
        ns = self._ns
        row = self._conn.execute(f"SELECT * FROM {ns}_raw_events WHERE id = ?", (event_id,)).fetchone()
        return self._row_to_raw(row) if row else None

    @locked_sqlite_operation
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
        """List raw events with optional filters, ordered by timestamp DESC.

        ``after`` / ``before`` are inclusive bounds.
        """
        ns = self._ns
        conditions: list[str] = []
        params: list[Any] = []
        if host is not None:
            conditions.append("host = ?")
            params.append(host)
        if session_id is not None:
            conditions.append("session_id = ?")
            params.append(session_id)
        if thread_id is not None:
            conditions.append("thread_id = ?")
            params.append(thread_id)
        if user is not None:
            conditions.append("user = ?")
            params.append(user)
        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type)
        if after is not None:
            conditions.append("timestamp >= ?")
            params.append(after.isoformat())
        if before is not None:
            conditions.append("timestamp <= ?")
            params.append(before.isoformat())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        rows = self._conn.execute(
            f"""SELECT * FROM {ns}_raw_events
                {where}
                ORDER BY timestamp DESC
                LIMIT ?""",
            params,
        ).fetchall()
        return [self._row_to_raw(r) for r in rows]

    @locked_sqlite_operation
    def get_raw_events_by_ids(self, event_ids: list[str]) -> list[RawEvent]:
        """Batch-fetch raw events by a list of IDs, used to obtain the actual occurred_at timestamps."""
        if not event_ids:
            return []
        ns = self._ns
        placeholders = ",".join("?" * len(event_ids))
        rows = self._conn.execute(
            f"SELECT * FROM {ns}_raw_events WHERE id IN ({placeholders})",
            event_ids,
        ).fetchall()
        return [self._row_to_raw(r) for r in rows]

    @locked_sqlite_operation
    def search_raw(self, query: str, *, limit: int = 10) -> list[RawEvent]:
        """FTS5 full-text search over raw event content."""
        ns = self._ns
        # Wrap as phrase so operators like '-' don't trigger NOT.
        safe_query = fts_match_phrase(query)
        rows = self._conn.execute(
            f"""SELECT e.* FROM {ns}_raw_events_fts f
                JOIN {ns}_raw_events e ON f.rowid = e.rowid
                WHERE f.{ns}_raw_events_fts MATCH ?
                ORDER BY rank
                LIMIT ?""",
            (safe_query, limit),
        ).fetchall()
        return [self._row_to_raw(r) for r in rows]

    @locked_sqlite_operation
    def delete_raw_before(self, before: datetime) -> int:
        """GC: delete events with ``timestamp < before``. Returns rows deleted."""
        ns = self._ns
        cur = self._conn.execute(
            f"DELETE FROM {ns}_raw_events WHERE timestamp < ?",
            (before.isoformat(),),
        )
        self._commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # M2 — Candidates
    # ------------------------------------------------------------------

    @locked_sqlite_operation
    def find_duplicate_candidate(self, assertion: str, raw_event_ids: list[str], subject_name: str) -> bool:
        """Whether an identical promoted candidate already exists.

        Check whether a candidate with the exact same assertion, raw_event_ids,
        and subject_name already exists with status 'promoted'.

        Used to prevent a duplicate candidate from being generated when an old
        raw_event gets re-scanned after a process restart. Only the 'promoted'
        status is checked, to avoid mistakenly skipping duplicate content that
        is still 'pending' (test scenarios).
        """
        if not raw_event_ids:
            return False
        ns = self._ns
        target_ids = frozenset(raw_event_ids)
        # Only look up candidates matching assertion + subject_name + status='promoted'
        rows = self._conn.execute(
            (
                f"SELECT raw_event_ids FROM {ns}_candidates "
                "WHERE assertion = ? AND subject_name = ? AND status = 'promoted'"
            ),
            (assertion, subject_name),
        ).fetchall()
        for row in rows:
            try:
                existing_ids = frozenset(json.loads(row[0]))
            except (json.JSONDecodeError, TypeError, ValueError):
                logger.warning("skipping promoted candidate with unreadable raw_event_ids", exc_info=True)
                continue
            if existing_ids == target_ids:
                return True
        return False

    @locked_sqlite_operation
    def save_candidate(self, candidate: Candidate) -> None:
        """Insert a new candidate. Strict insert; duplicate id → IntegrityError."""
        ns = self._ns
        self._conn.execute(
            f"""INSERT INTO {ns}_candidates
                (id, raw_event_ids, candidate_type, status, title,
                 assertion, verbatim_quote, quote_event_id,
                 subject_name, subject_entity_type, target_entity_id,
                 confidence, importance, recommended_action,
                 promotion_reason, extractor_version,
                 created_at, decided_at, decided_by, session_id, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                candidate.id,
                json.dumps(candidate.raw_event_ids, ensure_ascii=False),
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
                candidate.created_at.isoformat(),
                candidate.decided_at.isoformat() if candidate.decided_at else None,
                candidate.decided_by,
                candidate.session_id,
                json.dumps(candidate.payload, ensure_ascii=False),
            ),
        )
        self._commit()

    @locked_sqlite_operation
    def get_candidate(self, candidate_id: str) -> Candidate | None:
        ns = self._ns
        row = self._conn.execute(
            f"SELECT * FROM {ns}_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()
        return self._row_to_candidate(row) if row else None

    @locked_sqlite_operation
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
        ns = self._ns
        conditions: list[str] = []
        params: list[Any] = []
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if session_id is not None:
            conditions.append("session_id = ?")
            params.append(session_id)
        if target_entity_id is not None:
            conditions.append("target_entity_id = ?")
            params.append(target_entity_id)
        if after is not None:
            conditions.append("created_at >= ?")
            params.append(after.isoformat())
        if before is not None:
            conditions.append("created_at <= ?")
            params.append(before.isoformat())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        rows = self._conn.execute(
            f"""SELECT * FROM {ns}_candidates
                {where}
                ORDER BY created_at DESC
                LIMIT ?""",
            params,
        ).fetchall()
        return [self._row_to_candidate(r) for r in rows]

    @locked_sqlite_operation
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
        ns = self._ns
        sets: list[str] = ["status = ?"]
        params: list[Any] = [status]

        if decided_by is not None:
            sets.append("decided_by = ?")
            params.append(decided_by)
        if decided_at is not None:
            sets.append("decided_at = ?")
            params.append(decided_at.isoformat())
        if not isinstance(target_entity_id, _Unset):
            sets.append("target_entity_id = ?")
            params.append(target_entity_id)
        if promotion_reason is not None:
            sets.append("promotion_reason = ?")
            params.append(promotion_reason)

        params.append(candidate_id)
        cur = self._conn.execute(
            f"UPDATE {ns}_candidates SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        self._commit()
        return cur.rowcount > 0

    @locked_sqlite_operation
    def search_candidates(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[Candidate]:
        """FTS5 full-text search over title + assertion + verbatim_quote."""
        ns = self._ns
        safe_query = fts_match_phrase(query)
        rows = self._conn.execute(
            f"""SELECT c.* FROM {ns}_candidates_fts f
                JOIN {ns}_candidates c ON f.rowid = c.rowid
                WHERE f.{ns}_candidates_fts MATCH ?
                ORDER BY rank
                LIMIT ?""",
            (safe_query, limit),
        ).fetchall()
        return [self._row_to_candidate(r) for r in rows]

    # ------------------------------------------------------------------
    # M2 — Atoms
    # ------------------------------------------------------------------

    @locked_sqlite_operation
    def save_atom(self, atom: AtomCard) -> None:
        """Insert a new atom. Strict insert; duplicate id → IntegrityError."""
        ns = self._ns
        self._conn.execute(
            f"""INSERT INTO {ns}_atoms
                (id, entity_id, candidate_id, raw_event_ids,
                 assertion, verbatim_quote, quote_event_id, search_terms,
                 occurred_at, confidence, importance,
                 superseded_by, deprecated_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                atom.id,
                atom.entity_id,
                atom.candidate_id,
                json.dumps(atom.raw_event_ids, ensure_ascii=False),
                atom.assertion,
                atom.verbatim_quote,
                atom.quote_event_id,
                json.dumps(atom.search_terms, ensure_ascii=False),
                atom.occurred_at.isoformat(),
                atom.confidence,
                atom.importance,
                atom.superseded_by,
                atom.deprecated_at.isoformat() if atom.deprecated_at else None,
                atom.created_at.isoformat(),
            ),
        )
        self._commit()

    @locked_sqlite_operation
    def get_atom(self, atom_id: str) -> AtomCard | None:
        ns = self._ns
        row = self._conn.execute(
            f"SELECT * FROM {ns}_atoms WHERE id = ?",
            (atom_id,),
        ).fetchone()
        return self._row_to_atom(row) if row else None

    @locked_sqlite_operation
    def list_atoms(
        self,
        *,
        entity_id: str | None = None,
        importance: ImportanceLevel | None = None,
        include_deprecated: bool = False,
        limit: int = 100,
    ) -> list[AtomCard]:
        ns = self._ns
        conditions: list[str] = []
        params: list[Any] = []
        if entity_id is not None:
            conditions.append("entity_id = ?")
            params.append(entity_id)
        if importance is not None:
            conditions.append("importance = ?")
            params.append(importance)
        if not include_deprecated:
            conditions.append("deprecated_at IS NULL")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        rows = self._conn.execute(
            f"""SELECT * FROM {ns}_atoms
                {where}
                ORDER BY created_at DESC
                LIMIT ?""",
            params,
        ).fetchall()
        return [self._row_to_atom(r) for r in rows]

    @locked_sqlite_operation
    def supersede_atom(
        self,
        old_atom_id: str,
        *,
        new_atom_id: str,
        deprecated_at: datetime,
    ) -> bool:
        """Mark an active atom as superseded without overwriting an existing successor."""
        ns = self._ns
        cur = self._conn.execute(
            f"""UPDATE {ns}_atoms
                SET superseded_by = ?, deprecated_at = ?
                WHERE id = ? AND deprecated_at IS NULL""",
            (new_atom_id, deprecated_at.isoformat(), old_atom_id),
        )
        self._commit()
        return cur.rowcount > 0

    @locked_sqlite_operation
    def deprecate_atom(self, atom_id: str, *, deprecated_at: datetime) -> bool:
        ns = self._ns
        cur = self._conn.execute(
            f"UPDATE {ns}_atoms SET deprecated_at = ? WHERE id = ?",
            (deprecated_at.isoformat(), atom_id),
        )
        self._commit()
        return cur.rowcount > 0

    @locked_sqlite_operation
    def find_atom_by_signature(self, sig: str) -> AtomCard | None:
        """Globally find the first non-deprecated atom whose assertion signature matches ``sig``.

        Used for exact duplicate detection across entities. The signature is
        computed by the caller (check_duplicate) via ``_assertion_signature``
        and passed in; here we simply do a string comparison.
        LIMIT 1 bounds the query cost.
        """
        ns = self._ns
        row = self._conn.execute(
            f"""SELECT * FROM {ns}_atoms
                WHERE deprecated_at IS NULL
                ORDER BY created_at ASC
                LIMIT 200""",
        ).fetchall()
        # Compare signatures at the Python level, consistent with
        # check_duplicate's logic, to avoid false mismatches caused by
        # database-level charset/collation differences.
        from octop_memory.domain.alias import normalize_alias

        for r in row:
            atom = self._row_to_atom(r)
            if normalize_alias(atom.assertion) == sig:
                return atom
        return None

    @locked_sqlite_operation
    def migrate_atoms_to_entity(
        self,
        source_entity_id: str,
        target_entity_id: str,
    ) -> int:
        """Batch-migrate every non-deprecated atom under the source entity to the target entity.

        Performs the following in a single database transaction:
        1. Update entity_id to the target entity id for every non-deprecated
           atom under the source entity.
        2. For any assertion-signature duplicate that results under the
           target entity after migration, mark it deprecated (superseded_by
           pointing to the existing keeper under the target entity).

        Returns the number of atoms actually migrated (entity_id updated).
        """
        from octop_memory.domain.alias import normalize_alias

        ns = self._ns
        now = datetime.now(UTC)

        # Read every non-deprecated atom under the source entity
        source_atoms = self._conn.execute(
            f"""SELECT * FROM {ns}_atoms
                WHERE entity_id = ? AND deprecated_at IS NULL""",
            (source_entity_id,),
        ).fetchall()

        if not source_atoms:
            return 0

        # Read every non-deprecated atom under the target entity (for duplicate detection)
        target_atoms = self._conn.execute(
            f"""SELECT * FROM {ns}_atoms
                WHERE entity_id = ? AND deprecated_at IS NULL""",
            (target_entity_id,),
        ).fetchall()

        # Build a mapping from the target entity's assertion signature to atom_id
        target_sig_map: dict[str, str] = {}
        for r in target_atoms:
            atom = self._row_to_atom(r)
            sig = normalize_alias(atom.assertion)
            if sig and sig not in target_sig_map:
                target_sig_map[sig] = atom.id

        migrated = 0
        with self._conn:
            for r in source_atoms:
                atom = self._row_to_atom(r)
                sig = normalize_alias(atom.assertion)

                # Check whether this would duplicate an existing atom under the target entity
                if sig and sig in target_sig_map:
                    # Duplicate: mark the migrated atom deprecated, superseded_by -> keeper
                    keeper_id = target_sig_map[sig]
                    self._conn.execute(
                        f"""UPDATE {ns}_atoms
                            SET superseded_by = ?, deprecated_at = ?
                            WHERE id = ?""",
                        (keeper_id, now.isoformat(), atom.id),
                    )
                else:
                    # Not a duplicate: migrate to the target entity
                    self._conn.execute(
                        f"""UPDATE {ns}_atoms
                            SET entity_id = ?
                            WHERE id = ?""",
                        (target_entity_id, atom.id),
                    )
                    # Add the newly-migrated atom to target_sig_map to prevent
                    # duplicates within the same batch
                    if sig:
                        target_sig_map[sig] = atom.id
                    migrated += 1

        return migrated

    @locked_sqlite_operation
    def search_atoms(
        self,
        query: str,
        *,
        include_deprecated: bool = False,
        limit: int = 10,
    ) -> list[AtomCard]:
        """FTS5 full-text search over assertion + verbatim_quote + search_terms."""
        ns = self._ns
        safe_query = fts_match_phrase(query)
        deprecation_filter = "" if include_deprecated else "AND a.deprecated_at IS NULL"
        rows = self._conn.execute(
            f"""SELECT a.* FROM {ns}_atoms_fts f
                JOIN {ns}_atoms a ON f.rowid = a.rowid
                WHERE f.{ns}_atoms_fts MATCH ?
                  {deprecation_filter}
                ORDER BY rank
                LIMIT ?""",
            (safe_query, limit),
        ).fetchall()
        return [self._row_to_atom(r) for r in rows]

    @locked_sqlite_operation
    def search_atoms_by_time_range(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        entity_id: str | None = None,
        include_deprecated: bool = False,
        limit: int = 50,
    ) -> list[AtomCard]:
        ns = self._ns
        clauses: list[str] = []
        params: list[object] = []
        if start is not None:
            clauses.append("occurred_at >= ?")
            params.append(start.isoformat())
        if end is not None:
            clauses.append("occurred_at <= ?")
            params.append(end.isoformat())
        if entity_id is not None:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if not include_deprecated:
            clauses.append("deprecated_at IS NULL")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"""SELECT * FROM {ns}_atoms
                {where}
                ORDER BY occurred_at DESC
                LIMIT ?""",
            params,
        ).fetchall()
        return [self._row_to_atom(r) for r in rows]

    # ------------------------------------------------------------------
    # M2 — Entities (minimal)
    # ------------------------------------------------------------------

    @locked_sqlite_operation
    def save_entity(self, entity: Entity) -> None:
        """Insert a new entity. Strict insert; duplicate id → IntegrityError."""
        ns = self._ns
        self._conn.execute(
            f"""INSERT INTO {ns}_entities
                (id, entity_type, canonical_name, aliases,
                 atom_count, last_promoted_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                entity.id,
                entity.entity_type,
                entity.canonical_name,
                json.dumps(entity.aliases, ensure_ascii=False),
                entity.atom_count,
                entity.last_promoted_at.isoformat() if entity.last_promoted_at else None,
                entity.created_at.isoformat(),
            ),
        )
        self._commit()

    @locked_sqlite_operation
    def get_entity(self, entity_id: str) -> Entity | None:
        ns = self._ns
        row = self._conn.execute(
            f"SELECT * FROM {ns}_entities WHERE id = ?",
            (entity_id,),
        ).fetchone()
        return self._row_to_entity(row) if row else None

    @locked_sqlite_operation
    def find_entity_by_name(
        self,
        canonical_name: str,
        *,
        entity_type: EntityType | None = None,
    ) -> Entity | None:
        ns = self._ns
        if entity_type is not None:
            row = self._conn.execute(
                f"""SELECT * FROM {ns}_entities
                    WHERE canonical_name = ? COLLATE NOCASE AND entity_type = ?
                    LIMIT 1""",
                (canonical_name, entity_type),
            ).fetchone()
        else:
            row = self._conn.execute(
                f"""SELECT * FROM {ns}_entities
                    WHERE canonical_name = ? COLLATE NOCASE
                    LIMIT 1""",
                (canonical_name,),
            ).fetchone()
        return self._row_to_entity(row) if row else None

    @locked_sqlite_operation
    def list_entities(
        self,
        *,
        entity_type: EntityType | None = None,
        limit: int = 100,
    ) -> list[Entity]:
        ns = self._ns
        if entity_type is not None:
            rows = self._conn.execute(
                f"""SELECT * FROM {ns}_entities
                    WHERE entity_type = ?
                    ORDER BY canonical_name
                    LIMIT ?""",
                (entity_type, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"""SELECT * FROM {ns}_entities
                    ORDER BY canonical_name
                    LIMIT ?""",
                (limit,),
            ).fetchall()
        return [self._row_to_entity(r) for r in rows]

    @locked_sqlite_operation
    def bump_entity_atom_count(
        self,
        entity_id: str,
        *,
        delta: int,
        last_promoted_at: datetime | None = None,
    ) -> bool:
        ns = self._ns
        if last_promoted_at is not None:
            cur = self._conn.execute(
                f"""UPDATE {ns}_entities
                    SET atom_count = atom_count + ?,
                        last_promoted_at = ?
                    WHERE id = ?""",
                (delta, last_promoted_at.isoformat(), entity_id),
            )
        else:
            cur = self._conn.execute(
                f"""UPDATE {ns}_entities
                    SET atom_count = atom_count + ?
                    WHERE id = ?""",
                (delta, entity_id),
            )
        self._commit()
        return cur.rowcount > 0

    @locked_sqlite_operation
    def update_entity_canonical_name(self, entity_id: str, canonical_name: str) -> bool:
        ns = self._ns
        cur = self._conn.execute(
            f"UPDATE {ns}_entities SET canonical_name = ? WHERE id = ?",
            (canonical_name, entity_id),
        )
        self._commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # M2 — Aliases
    # ------------------------------------------------------------------

    @locked_sqlite_operation
    def save_alias(self, alias: Alias) -> None:
        """Insert alias mapping. Duplicate (alias, entity_id) → no-op."""
        ns = self._ns
        self._conn.execute(
            f"""INSERT OR IGNORE INTO {ns}_aliases
                (alias, entity_id, entity_type, created_by, created_at)
                VALUES (?, ?, ?, ?, ?)""",
            (
                alias.alias,
                alias.entity_id,
                alias.entity_type,
                alias.created_by,
                alias.created_at.isoformat(),
            ),
        )
        self._commit()

    @locked_sqlite_operation
    def find_entity_by_alias(self, alias: str) -> Entity | None:
        """Resolve a (normalized) alias to its entity, or ``None`` if not found.

        The caller is responsible for normalization (lowercase + whitespace
        collapse). This method does **not** auto-normalize so that callers
        can decide their own normalization scheme.
        """
        ns = self._ns
        row = self._conn.execute(
            f"""SELECT e.* FROM {ns}_aliases a
                JOIN {ns}_entities e ON a.entity_id = e.id
                WHERE a.alias = ?
                LIMIT 1""",
            (alias,),
        ).fetchone()
        return self._row_to_entity(row) if row else None

    @locked_sqlite_operation
    def list_aliases(
        self,
        *,
        entity_id: str | None = None,
        limit: int = 100,
    ) -> list[Alias]:
        ns = self._ns
        if entity_id is not None:
            rows = self._conn.execute(
                f"""SELECT * FROM {ns}_aliases
                    WHERE entity_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?""",
                (entity_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"""SELECT * FROM {ns}_aliases
                    ORDER BY created_at DESC
                    LIMIT ?""",
                (limit,),
            ).fetchall()
        return [self._row_to_alias(r) for r in rows]

    # ------------------------------------------------------------------
    # M3 - Entity Pages (long-form summary; D32-D37)
    # ------------------------------------------------------------------

    @locked_sqlite_operation
    def upsert_entity_page(self, page: EntityPage) -> None:
        """Insert or replace the page row keyed by ``entity_id``.

        Implementation: ``INSERT … ON CONFLICT(entity_id) DO UPDATE``
        so callers can pass a freshly-built :class:`EntityPage`
        regardless of whether one already exists. The row's ``id``
        column is left untouched on update — only the data fields are
        rewritten.
        """
        ns = self._ns
        self._conn.execute(
            f"""INSERT INTO {ns}_entity_pages
                (id, entity_id, summary_markdown, headline, topics,
                 dirty, regen_attempt_count, summary_version,
                 last_regen_at, last_user_edit_at,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    summary_markdown = excluded.summary_markdown,
                    headline = excluded.headline,
                    topics = excluded.topics,
                    dirty = excluded.dirty,
                    regen_attempt_count = excluded.regen_attempt_count,
                    summary_version = excluded.summary_version,
                    last_regen_at = excluded.last_regen_at,
                    last_user_edit_at = excluded.last_user_edit_at,
                    updated_at = excluded.updated_at
            """,
            (
                page.id,
                page.entity_id,
                page.summary_markdown,
                page.headline,
                json.dumps(page.topics, ensure_ascii=False),
                1 if page.dirty else 0,
                page.regen_attempt_count,
                page.summary_version,
                page.last_regen_at.isoformat() if page.last_regen_at else None,
                page.last_user_edit_at.isoformat() if page.last_user_edit_at else None,
                page.created_at.isoformat(),
                page.updated_at.isoformat(),
            ),
        )
        self._commit()

    @locked_sqlite_operation
    def get_entity_page(self, entity_id: str) -> EntityPage | None:
        ns = self._ns
        row = self._conn.execute(
            f"SELECT * FROM {ns}_entity_pages WHERE entity_id = ?",
            (entity_id,),
        ).fetchone()
        return self._row_to_entity_page(row) if row else None

    @locked_sqlite_operation
    def count_stats(self) -> dict[str, int]:
        ns = self._ns

        def _count(sql: str) -> int:
            return int(self._conn.execute(sql).fetchone()[0])

        return {
            "raw_events": _count(f"SELECT COUNT(*) FROM {ns}_raw_events"),
            "atoms": _count(f"SELECT COUNT(*) FROM {ns}_atoms"),
            "entities": _count(f"SELECT COUNT(*) FROM {ns}_entities"),
            "dirty_pages": _count(f"SELECT COUNT(*) FROM {ns}_entity_pages WHERE dirty = 1"),
        }

    @locked_sqlite_operation
    def list_dirty_entity_pages(self, *, limit: int = 50) -> list[EntityPage]:
        ns = self._ns
        # Sort: never-regenerated rows first (last_regen_at NULL), then oldest
        # successful regen. This gives brand-new entities priority over
        # stale-but-regenerated ones.
        rows = self._conn.execute(
            f"""SELECT * FROM {ns}_entity_pages
                WHERE dirty = 1
                ORDER BY (last_regen_at IS NULL) DESC,
                         last_regen_at ASC,
                         updated_at ASC
                LIMIT ?""",
            (limit,),
        ).fetchall()
        return [self._row_to_entity_page(r) for r in rows]

    @locked_sqlite_operation
    def mark_entity_page_dirty(self, entity_id: str, *, when: datetime) -> None:
        """Mark dirty (or insert a stub row + dirty if absent). Idempotent."""
        ns = self._ns
        cur = self._conn.execute(
            f"""UPDATE {ns}_entity_pages
                SET dirty = 1, updated_at = ?
                WHERE entity_id = ?""",
            (when.isoformat(), entity_id),
        )
        if cur.rowcount == 0:
            # No existing row → insert a dirty stub. Page id is just
            # the entity_id with a stable prefix so collisions are
            # impossible across entities.
            self._conn.execute(
                f"""INSERT INTO {ns}_entity_pages
                    (id, entity_id, summary_markdown, headline, topics,
                     dirty, regen_attempt_count, summary_version,
                     last_regen_at, last_user_edit_at,
                     created_at, updated_at)
                    VALUES (?, ?, '', '', '[]', 1, 0, 0, NULL, NULL, ?, ?)
                """,
                (
                    f"page_{entity_id}",
                    entity_id,
                    when.isoformat(),
                    when.isoformat(),
                ),
            )
        self._commit()

    @locked_sqlite_operation
    def apply_entity_page_regen(
        self,
        entity_id: str,
        *,
        summary_markdown: str,
        headline: str,
        topics: list[str],
        when: datetime,
    ) -> bool:
        ns = self._ns
        cur = self._conn.execute(
            f"""UPDATE {ns}_entity_pages
                SET summary_markdown = ?,
                    headline = ?,
                    topics = ?,
                    dirty = 0,
                    regen_attempt_count = 0,
                    summary_version = summary_version + 1,
                    last_regen_at = ?,
                    updated_at = ?
                WHERE entity_id = ?""",
            (
                summary_markdown,
                headline,
                json.dumps(topics, ensure_ascii=False),
                when.isoformat(),
                when.isoformat(),
                entity_id,
            ),
        )
        self._commit()
        return cur.rowcount > 0

    @locked_sqlite_operation
    def record_entity_page_regen_failure(
        self,
        entity_id: str,
        *,
        when: datetime,
    ) -> bool:
        ns = self._ns
        cur = self._conn.execute(
            f"""UPDATE {ns}_entity_pages
                SET regen_attempt_count = regen_attempt_count + 1,
                    dirty = 1,
                    updated_at = ?
                WHERE entity_id = ?""",
            (when.isoformat(), entity_id),
        )
        self._commit()
        return cur.rowcount > 0

    @locked_sqlite_operation
    def apply_entity_page_user_edit(
        self,
        entity_id: str,
        *,
        summary_markdown: str,
        when: datetime,
    ) -> bool:
        ns = self._ns
        cur = self._conn.execute(
            f"""UPDATE {ns}_entity_pages
                SET summary_markdown = ?,
                    summary_version = summary_version + 1,
                    last_user_edit_at = ?,
                    updated_at = ?
                WHERE entity_id = ?""",
            (
                summary_markdown,
                when.isoformat(),
                when.isoformat(),
                entity_id,
            ),
        )
        self._commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # M4 — Thread Active-Entity Stack (D41a + D41b)
    # ------------------------------------------------------------------

    @locked_sqlite_operation
    def upsert_active_entity(self, record: ActiveEntity) -> None:
        ns = self._ns
        self._conn.execute(
            f"""INSERT INTO {ns}_thread_active_entities
                (thread_id, entity_id, last_seen_at, source)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(thread_id, entity_id) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    source = excluded.source
            """,
            (
                record.thread_id,
                record.entity_id,
                record.last_seen_at.isoformat(),
                record.source,
            ),
        )
        self._commit()

    @locked_sqlite_operation
    def list_active_entities(
        self,
        thread_id: str,
        *,
        limit: int = 5,
    ) -> list[ActiveEntity]:
        ns = self._ns
        rows = self._conn.execute(
            f"""SELECT thread_id, entity_id, last_seen_at, source
                FROM {ns}_thread_active_entities
                WHERE thread_id = ?
                ORDER BY last_seen_at DESC
                LIMIT ?""",
            (thread_id, limit),
        ).fetchall()
        return [self._row_to_active_entity(r) for r in rows]

    @locked_sqlite_operation
    def evict_active_entities(
        self,
        thread_id: str,
        *,
        keep: int = 5,
    ) -> int:
        ns = self._ns
        # SQLite doesn't have ROW_NUMBER() in our supported version range,
        # so do this via a sub-SELECT of the keep-set.
        cur = self._conn.execute(
            f"""DELETE FROM {ns}_thread_active_entities
                WHERE thread_id = ?
                  AND entity_id NOT IN (
                    SELECT entity_id FROM {ns}_thread_active_entities
                    WHERE thread_id = ?
                    ORDER BY last_seen_at DESC
                    LIMIT ?
                  )""",
            (thread_id, thread_id, keep),
        )
        self._commit()
        return cur.rowcount

    @staticmethod
    def _row_to_active_entity(row: sqlite3.Row) -> ActiveEntity:
        return ActiveEntity(
            thread_id=str(row["thread_id"]),
            entity_id=str(row["entity_id"]),
            last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
            source=row["source"] or "recall_hit",
        )

    # ------------------------------------------------------------------
    # M2 — Journal (append-only)
    # ------------------------------------------------------------------

    @locked_sqlite_operation
    def append_journal(self, entry: JournalEntry) -> None:
        """Append a journal entry. Pipeline rows are expired by ``delete_journal``."""
        ns = self._ns
        self._conn.execute(
            f"""INSERT INTO {ns}_journal
                (id, timestamp, action, actor,
                 target_entity_id, target_atom_id, target_candidate_id,
                 before, after, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.id,
                entry.timestamp.isoformat(),
                entry.action,
                entry.actor,
                entry.target_entity_id,
                entry.target_atom_id,
                entry.target_candidate_id,
                json.dumps(entry.before, ensure_ascii=False) if entry.before is not None else None,
                json.dumps(entry.after, ensure_ascii=False) if entry.after is not None else None,
                entry.note,
            ),
        )
        self._commit()

    @locked_sqlite_operation
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
        ns = self._ns
        conditions: list[str] = []
        params: list[Any] = []
        if action is not None:
            conditions.append("action = ?")
            params.append(action)
        if target_entity_id is not None:
            conditions.append("target_entity_id = ?")
            params.append(target_entity_id)
        if target_atom_id is not None:
            conditions.append("target_atom_id = ?")
            params.append(target_atom_id)
        if target_candidate_id is not None:
            conditions.append("target_candidate_id = ?")
            params.append(target_candidate_id)
        if after is not None:
            conditions.append("timestamp >= ?")
            params.append(after.isoformat())
        if before is not None:
            conditions.append("timestamp <= ?")
            params.append(before.isoformat())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        rows = self._conn.execute(
            f"""SELECT * FROM {ns}_journal
                {where}
                ORDER BY timestamp DESC
                LIMIT ?""",
            params,
        ).fetchall()
        return [self._row_to_journal(r) for r in rows]

    @locked_sqlite_operation
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
        ns = self._ns
        placeholders = ",".join("?" * len(actions))
        params: list[Any] = [before.isoformat(), *actions, limit]
        subquery = f"""
            SELECT id FROM {ns}_journal
            WHERE timestamp < ? AND action IN ({placeholders})
            ORDER BY timestamp ASC
            LIMIT ?
        """
        if dry_run:
            row = self._conn.execute(f"SELECT COUNT(*) FROM ({subquery})", params).fetchone()
            return int(row[0]) if row else 0
        cur = self._conn.execute(f"DELETE FROM {ns}_journal WHERE id IN ({subquery})", params)
        self._commit()
        return int(cur.rowcount)

    @locked_sqlite_operation
    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute(
            f"SELECT value FROM {self._ns}_meta WHERE key = ?",
            (key,),
        ).fetchone()
        return str(row[0]) if row is not None else None

    @locked_sqlite_operation
    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            f"INSERT INTO {self._ns}_meta (key, value) VALUES (?, ?) "
            f"ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._commit()

    # ------------------------------------------------------------------
    # M5 — Episodes (L2.5 diary layer)
    # ------------------------------------------------------------------

    @locked_sqlite_operation
    def save_episode(self, episode: Episode) -> None:
        """Insert a new Episode. Strict insert; duplicate id → IntegrityError."""
        ns = self._ns
        self._conn.execute(
            f"""INSERT INTO {ns}_episodes
                (id, raw_event_ids, occurred_at, summary, verbatim_quote, quote_event_id,
                 emotion, intensity, people, topics, extractor_version, session_id,
                 digest_ids, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                episode.id,
                json.dumps(episode.raw_event_ids, ensure_ascii=False),
                as_utc(episode.occurred_at).isoformat(),
                episode.summary,
                episode.verbatim_quote,
                episode.quote_event_id,
                episode.emotion,
                int(episode.intensity),
                json.dumps(episode.people, ensure_ascii=False),
                json.dumps(episode.topics, ensure_ascii=False),
                episode.extractor_version,
                episode.session_id,
                json.dumps(episode.digest_ids, ensure_ascii=False),
                as_utc(episode.created_at).isoformat(),
            ),
        )
        self._commit()

    @locked_sqlite_operation
    def get_episode(self, episode_id: str) -> Episode | None:
        ns = self._ns
        row = self._conn.execute(
            f"SELECT * FROM {ns}_episodes WHERE id = ?",
            (episode_id,),
        ).fetchone()
        return self._row_to_episode(row) if row else None

    @locked_sqlite_operation
    def list_episodes(
        self,
        *,
        session_id: str | None = None,
        emotion: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[Episode]:
        ns = self._ns
        clauses: list[str] = []
        params: list[Any] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if emotion is not None:
            clauses.append("emotion = ?")
            params.append(emotion)
        if after is not None:
            clauses.append("occurred_at >= ?")
            params.append(as_utc(after).isoformat())
        if before is not None:
            clauses.append("occurred_at < ?")
            params.append(as_utc(before).isoformat())
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"""SELECT * FROM {ns}_episodes
                {where}
                ORDER BY occurred_at DESC
                LIMIT ?""",
            params,
        ).fetchall()
        return [self._row_to_episode(r) for r in rows]

    @locked_sqlite_operation
    def search_episodes(self, query: str, *, limit: int = 10) -> list[Episode]:
        """FTS5 over summary + verbatim_quote + people + topics."""
        ns = self._ns
        safe_query = fts_match_phrase(query)
        rows = self._conn.execute(
            f"""SELECT e.* FROM {ns}_episodes_fts f
                JOIN {ns}_episodes e ON f.rowid = e.rowid
                WHERE f.{ns}_episodes_fts MATCH ?
                ORDER BY rank
                LIMIT ?""",
            (safe_query, limit),
        ).fetchall()
        return [self._row_to_episode(r) for r in rows]

    @locked_sqlite_operation
    def list_episodes_in_range(
        self,
        *,
        start: datetime,
        end: datetime,
        limit: int = 500,
    ) -> list[Episode]:
        """List episodes whose occurred_at falls in ``[start, end)``.

        Used by the digest aggregator. Ordered by occurred_at ASC so
        the markdown reads chronologically.
        """
        ns = self._ns
        rows = self._conn.execute(
            f"""SELECT * FROM {ns}_episodes
                WHERE occurred_at >= ? AND occurred_at < ?
                ORDER BY occurred_at ASC
                LIMIT ?""",
            (as_utc(start).isoformat(), as_utc(end).isoformat(), limit),
        ).fetchall()
        return [self._row_to_episode(r) for r in rows]

    @locked_sqlite_operation
    def upsert_digest(self, digest: DigestRecord) -> None:
        """Insert or replace a digest row keyed by (period_kind, period_key).

        Re-running the digest for the same period overwrites the prior
        markdown / episode_ids / updated_at. The original ``id`` and
        ``created_at`` are preserved if the row already existed.
        """
        ns = self._ns
        existing = self._conn.execute(
            f"SELECT id, created_at FROM {ns}_digests WHERE period_kind = ? AND period_key = ?",
            (digest.period_kind, digest.period_key),
        ).fetchone()
        if existing is not None:
            self._conn.execute(
                f"""UPDATE {ns}_digests SET
                       period_start = ?, period_end = ?, markdown = ?,
                       episode_ids = ?, llm_version = ?, updated_at = ?
                     WHERE id = ?""",
                (
                    digest.period_start.isoformat(),
                    digest.period_end.isoformat(),
                    digest.markdown,
                    json.dumps(digest.episode_ids, ensure_ascii=False),
                    digest.llm_version,
                    digest.updated_at.isoformat(),
                    existing["id"],
                ),
            )
        else:
            self._conn.execute(
                f"""INSERT INTO {ns}_digests
                    (id, period_kind, period_key, period_start, period_end,
                     markdown, episode_ids, llm_version, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    digest.id,
                    digest.period_kind,
                    digest.period_key,
                    digest.period_start.isoformat(),
                    digest.period_end.isoformat(),
                    digest.markdown,
                    json.dumps(digest.episode_ids, ensure_ascii=False),
                    digest.llm_version,
                    digest.created_at.isoformat(),
                    digest.updated_at.isoformat(),
                ),
            )
        self._commit()

    @locked_sqlite_operation
    def get_digest(self, period_kind: DigestPeriod, period_key: str) -> DigestRecord | None:
        ns = self._ns
        row = self._conn.execute(
            f"SELECT * FROM {ns}_digests WHERE period_kind = ? AND period_key = ?",
            (period_kind, period_key),
        ).fetchone()
        return self._row_to_digest(row) if row else None

    @locked_sqlite_operation
    def list_digests(
        self,
        *,
        period_kind: DigestPeriod | None = None,
        limit: int = 50,
    ) -> list[DigestRecord]:
        ns = self._ns
        if period_kind is not None:
            rows = self._conn.execute(
                f"""SELECT * FROM {ns}_digests
                    WHERE period_kind = ?
                    ORDER BY period_start DESC
                    LIMIT ?""",
                (period_kind, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"""SELECT * FROM {ns}_digests
                    ORDER BY period_start DESC
                    LIMIT ?""",
                (limit,),
            ).fetchall()
        return [self._row_to_digest(r) for r in rows]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> MemoryNode:
        # ``metadata`` column may be missing on legacy rows that were
        # ALTERed to add the column (the DEFAULT applies to new inserts
        # but pre-existing rows get NULL). Normalise to ``{}``.
        try:
            raw_metadata = row["metadata"]
        except (IndexError, KeyError):
            raw_metadata = None
        metadata: dict[str, Any] = json.loads(raw_metadata) if raw_metadata else {}
        keys = set(row.keys())
        atom_id = str(row["atom_id"]) if "atom_id" in keys and row["atom_id"] is not None else None
        atom_content = row["atom_content"] if "atom_content" in keys else None
        return MemoryNode(
            id=str(row["id"]),
            parent_id=str(row["parent_id"]) if row["parent_id"] is not None else None,
            level=row["level"],
            content=atom_content if atom_id is not None and atom_content is not None else row["content"],
            topic=row["topic"],
            conversation_id=str(row["conversation_id"]) if row["conversation_id"] is not None else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=metadata,
            atom_id=atom_id,
        )

    @staticmethod
    def _row_to_raw(row: sqlite3.Row) -> RawEvent:
        raw_payload = row["payload"]
        payload: dict[str, Any] = json.loads(raw_payload) if raw_payload else {}
        return RawEvent(
            id=str(row["id"]),
            host=row["host"],
            session_id=str(row["session_id"]) if row["session_id"] is not None else None,
            thread_id=str(row["thread_id"]) if row["thread_id"] is not None else None,
            user=row["user"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            event_type=row["event_type"],
            content=row["content"],
            payload=payload,
        )

    @staticmethod
    def _row_to_candidate(row: sqlite3.Row) -> Candidate:
        return Candidate(
            id=str(row["id"]),
            raw_event_ids=json.loads(row["raw_event_ids"]),
            candidate_type=row["candidate_type"],
            status=row["status"],
            title=row["title"],
            assertion=row["assertion"],
            verbatim_quote=row["verbatim_quote"],
            quote_event_id=str(row["quote_event_id"]),
            subject_name=row["subject_name"],
            subject_entity_type=row["subject_entity_type"],
            target_entity_id=str(row["target_entity_id"]) if row["target_entity_id"] is not None else None,
            confidence=row["confidence"],
            importance=row["importance"],
            recommended_action=row["recommended_action"],
            promotion_reason=row["promotion_reason"],
            extractor_version=row["extractor_version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            decided_at=datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else None,
            decided_by=row["decided_by"],
            session_id=str(row["session_id"]) if row["session_id"] is not None else None,
            payload=json.loads(row["payload"]) if row["payload"] else {},
        )

    @staticmethod
    def _row_to_atom(row: sqlite3.Row) -> AtomCard:
        return AtomCard(
            id=str(row["id"]),
            entity_id=str(row["entity_id"]),
            candidate_id=str(row["candidate_id"]),
            raw_event_ids=json.loads(row["raw_event_ids"]),
            assertion=row["assertion"],
            verbatim_quote=row["verbatim_quote"],
            quote_event_id=str(row["quote_event_id"]),
            search_terms=json.loads(row["search_terms"]),
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            confidence=row["confidence"],
            importance=row["importance"],
            superseded_by=str(row["superseded_by"]) if row["superseded_by"] is not None else None,
            deprecated_at=datetime.fromisoformat(row["deprecated_at"]) if row["deprecated_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> Entity:
        return Entity(
            id=str(row["id"]),
            entity_type=row["entity_type"],
            canonical_name=row["canonical_name"],
            aliases=json.loads(row["aliases"]) if row["aliases"] else [],
            atom_count=int(row["atom_count"]),
            last_promoted_at=datetime.fromisoformat(row["last_promoted_at"]) if row["last_promoted_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_entity_page(row: sqlite3.Row) -> EntityPage:
        return EntityPage(
            id=str(row["id"]),
            entity_id=str(row["entity_id"]),
            summary_markdown=row["summary_markdown"] or "",
            headline=row["headline"] or "",
            topics=json.loads(row["topics"]) if row["topics"] else [],
            dirty=bool(row["dirty"]),
            regen_attempt_count=int(row["regen_attempt_count"]),
            summary_version=int(row["summary_version"]),
            last_regen_at=datetime.fromisoformat(row["last_regen_at"]) if row["last_regen_at"] else None,
            last_user_edit_at=datetime.fromisoformat(row["last_user_edit_at"]) if row["last_user_edit_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _row_to_alias(row: sqlite3.Row) -> Alias:
        return Alias(
            alias=row["alias"],
            entity_id=str(row["entity_id"]),
            entity_type=row["entity_type"],
            created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_journal(row: sqlite3.Row) -> JournalEntry:
        before_raw = row["before"]
        after_raw = row["after"]
        return JournalEntry(
            id=str(row["id"]),
            timestamp=datetime.fromisoformat(row["timestamp"]),
            action=row["action"],
            actor=row["actor"],
            target_entity_id=str(row["target_entity_id"]) if row["target_entity_id"] is not None else None,
            target_atom_id=str(row["target_atom_id"]) if row["target_atom_id"] is not None else None,
            target_candidate_id=str(row["target_candidate_id"]) if row["target_candidate_id"] is not None else None,
            before=json.loads(before_raw) if before_raw else None,
            after=json.loads(after_raw) if after_raw else None,
            note=row["note"] or "",
        )

    @staticmethod
    def _row_to_episode(row: sqlite3.Row) -> Episode:
        return Episode(
            id=str(row["id"]),
            raw_event_ids=json.loads(row["raw_event_ids"]) if row["raw_event_ids"] else [],
            occurred_at=parse_datetime_utc(row["occurred_at"]),
            summary=row["summary"],
            verbatim_quote=row["verbatim_quote"],
            quote_event_id=str(row["quote_event_id"]),
            emotion=row["emotion"],
            intensity=int(row["intensity"]),
            people=json.loads(row["people"]) if row["people"] else [],
            topics=json.loads(row["topics"]) if row["topics"] else [],
            extractor_version=row["extractor_version"],
            session_id=str(row["session_id"]) if row["session_id"] is not None else None,
            digest_ids=json.loads(row["digest_ids"]) if row["digest_ids"] else [],
            created_at=parse_datetime_utc(row["created_at"]),
        )

    @staticmethod
    def _row_to_digest(row: sqlite3.Row) -> DigestRecord:
        return DigestRecord(
            id=str(row["id"]),
            period_kind=row["period_kind"],
            period_key=row["period_key"],
            period_start=datetime.fromisoformat(row["period_start"]),
            period_end=datetime.fromisoformat(row["period_end"]),
            markdown=row["markdown"] or "",
            episode_ids=json.loads(row["episode_ids"]) if row["episode_ids"] else [],
            llm_version=row["llm_version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
