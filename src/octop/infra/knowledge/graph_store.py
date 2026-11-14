"""Entity and relation rows extracted from knowledge-base chunks.

The graph is derived index data, stored next to the vector index: a
``graph.sqlite`` sidecar per knowledge base, or ``public.knowledge_graph_*``
tables when the control plane is PostgreSQL. Rows are kept per chunk and
merged by normalized entity name when read, so replacing or deleting one
document never leaves orphans behind.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from octop.config import DatabaseConfig
from octop.infra.utils.paths import PathLayout

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"

_IN_BATCH = 400


def entity_key(name: str) -> str:
    """Normalized identity of an entity name (case and spacing insensitive)."""
    return " ".join(str(name or "").split()).casefold()


@dataclass(frozen=True)
class ChunkEntity:
    name: str
    type: str = ""
    description: str = ""


@dataclass(frozen=True)
class ChunkRelation:
    source: str
    target: str
    label: str
    description: str = ""
    strength: float = 5.0


@dataclass(frozen=True)
class ChunkGraph:
    """What one chunk contributed."""

    ordinal: int
    entities: tuple[ChunkEntity, ...] = ()
    relations: tuple[ChunkRelation, ...] = ()


@dataclass(frozen=True)
class GraphEntity:
    key: str
    name: str
    type: str
    description: str
    mentions: int


@dataclass(frozen=True)
class GraphRelation:
    source: str
    target: str
    label: str
    description: str
    weight: float
    chunks: tuple[tuple[str, int], ...] = field(default=())


@dataclass(frozen=True)
class GraphDocumentState:
    status: str
    error: str = ""


class KnowledgeGraphStore:
    """Graph rows of one knowledge base. Subclasses supply the connection."""

    _entities = "knowledge_graph_entities"
    _relations = "knowledge_graph_relations"
    _documents = "knowledge_graph_documents"
    _mark = "?"

    def __init__(self, kb_id: str) -> None:
        self._kb_id = kb_id

    # -- connection plumbing -------------------------------------------------

    def _connect(self) -> Any:
        raise NotImplementedError

    def _present(self) -> bool:
        """False when nothing was ever written, so reads can skip the storage."""
        return True

    def _prepare(self, conn: Any) -> None:
        for statement in (
            f"""
            CREATE TABLE IF NOT EXISTS {self._entities} (
                kb_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                name_key TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (kb_id, doc_id, ordinal, name_key)
            )
            """,
            f"""
            CREATE INDEX IF NOT EXISTS idx_knowledge_graph_entities_key
            ON {self._entities} (kb_id, name_key)
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self._relations} (
                kb_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                source_key TEXT NOT NULL,
                target_key TEXT NOT NULL,
                label TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                strength REAL NOT NULL DEFAULT 5,
                PRIMARY KEY (kb_id, doc_id, ordinal, source_key, target_key, label)
            )
            """,
            f"""
            CREATE INDEX IF NOT EXISTS idx_knowledge_graph_relations_source
            ON {self._relations} (kb_id, source_key)
            """,
            f"""
            CREATE INDEX IF NOT EXISTS idx_knowledge_graph_relations_target
            ON {self._relations} (kb_id, target_key)
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self._documents} (
                kb_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (kb_id, doc_id)
            )
            """,
        ):
            conn.execute(statement)

    @contextmanager
    def _session(self) -> Iterator[Any]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _sql(self, statement: str) -> str:
        if self._mark == "?":
            return statement
        # psycopg reads a bare % as a placeholder, so literal ones are doubled.
        return statement.replace("%", "%%").replace("?", self._mark)

    def _fetch(self, statement: str, params: Sequence[object] = ()) -> list[tuple[Any, ...]]:
        if not self._present():
            return []
        with self._session() as conn:
            rows = conn.execute(self._sql(statement), tuple(params)).fetchall()
        return [tuple(row) for row in rows]

    def _fetch_in(
        self, statement: str, keys: Sequence[str], *, repeat: int = 1
    ) -> list[tuple[Any, ...]]:
        """Run *statement* once per batch of keys; ``{keys}`` expands to placeholders."""
        rows: list[tuple[Any, ...]] = []
        unique = list(dict.fromkeys(keys))
        for start in range(0, len(unique), _IN_BATCH):
            batch = unique[start : start + _IN_BATCH]
            marks = ",".join("?" for _ in batch)
            rows.extend(
                self._fetch(
                    statement.replace("{keys}", marks),
                    [self._kb_id, *(batch * repeat)],
                )
            )
        return rows

    # -- writes --------------------------------------------------------------

    def _delete_rows(self, conn: Any, doc_id: str) -> None:
        for table in (self._entities, self._relations):
            conn.execute(
                self._sql(f"DELETE FROM {table} WHERE kb_id = ? AND doc_id = ?"),
                (self._kb_id, doc_id),
            )

    def _set_state(self, conn: Any, doc_id: str, status: str, error: str) -> None:
        conn.execute(
            self._sql(f"DELETE FROM {self._documents} WHERE kb_id = ? AND doc_id = ?"),
            (self._kb_id, doc_id),
        )
        conn.execute(
            self._sql(
                f"INSERT INTO {self._documents}(kb_id, doc_id, status, error) VALUES (?, ?, ?, ?)"
            ),
            (self._kb_id, doc_id, status, error),
        )

    def replace_document(
        self, doc_id: str, chunks: Sequence[ChunkGraph], *, error: str = ""
    ) -> None:
        """Atomically replace everything one document contributed and mark it ready."""
        entity_rows: dict[tuple[int, str], tuple[object, ...]] = {}
        relation_rows: dict[tuple[int, str, str, str], tuple[object, ...]] = {}
        for chunk in chunks:
            for entity in chunk.entities:
                key = entity_key(entity.name)
                if key:
                    entity_rows.setdefault(
                        (chunk.ordinal, key),
                        (
                            self._kb_id,
                            doc_id,
                            chunk.ordinal,
                            key,
                            " ".join(entity.name.split()),
                            entity.type,
                            entity.description,
                        ),
                    )
            for relation in chunk.relations:
                source, target = entity_key(relation.source), entity_key(relation.target)
                if not source or not target or source == target or not relation.label:
                    continue
                relation_rows.setdefault(
                    (chunk.ordinal, source, target, relation.label),
                    (
                        self._kb_id,
                        doc_id,
                        chunk.ordinal,
                        source,
                        target,
                        relation.label,
                        relation.description,
                        float(relation.strength),
                    ),
                )
        with self._session() as conn:
            self._delete_rows(conn, doc_id)
            cursor = conn.cursor()
            if entity_rows:
                cursor.executemany(
                    self._sql(
                        f"INSERT INTO {self._entities}"
                        "(kb_id, doc_id, ordinal, name_key, name, type, description) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)"
                    ),
                    list(entity_rows.values()),
                )
            if relation_rows:
                cursor.executemany(
                    self._sql(
                        f"INSERT INTO {self._relations}"
                        "(kb_id, doc_id, ordinal, source_key, target_key, label, "
                        "description, strength) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    list(relation_rows.values()),
                )
            self._set_state(conn, doc_id, STATUS_READY, error)

    def mark_document(self, doc_id: str, status: str, *, error: str = "") -> None:
        """Record a document's graph state; anything but ``ready`` drops its rows."""
        with self._session() as conn:
            if status != STATUS_READY:
                self._delete_rows(conn, doc_id)
            self._set_state(conn, doc_id, status, error)

    def delete_document(self, doc_id: str) -> None:
        if not self._present():
            return
        with self._session() as conn:
            self._delete_rows(conn, doc_id)
            conn.execute(
                self._sql(f"DELETE FROM {self._documents} WHERE kb_id = ? AND doc_id = ?"),
                (self._kb_id, doc_id),
            )

    def clear(self) -> None:
        """Drop the whole graph of this knowledge base."""
        if not self._present():
            return
        with self._session() as conn:
            for table in (self._entities, self._relations, self._documents):
                conn.execute(self._sql(f"DELETE FROM {table} WHERE kb_id = ?"), (self._kb_id,))

    # -- reads ---------------------------------------------------------------

    def document_states(self) -> dict[str, GraphDocumentState]:
        rows = self._fetch(
            f"SELECT doc_id, status, error FROM {self._documents} WHERE kb_id = ?",
            (self._kb_id,),
        )
        return {
            str(doc_id): GraphDocumentState(str(status), str(error or ""))
            for doc_id, status, error in rows
        }

    def exists(self) -> bool:
        """True once a graph was built here (even if every document later left it)."""
        rows = self._fetch(
            f"SELECT 1 FROM {self._documents} WHERE kb_id = ? LIMIT 1", (self._kb_id,)
        )
        return bool(rows)

    def counts(self) -> tuple[int, int]:
        """Return ``(entities, relations)`` after merging by name."""
        entities = self._fetch(
            f"SELECT COUNT(DISTINCT name_key) FROM {self._entities} WHERE kb_id = ?",
            (self._kb_id,),
        )
        relations = self._fetch(
            "SELECT COUNT(*) FROM (SELECT DISTINCT source_key, target_key, label "
            f"FROM {self._relations} WHERE kb_id = ?) AS merged",
            (self._kb_id,),
        )
        return (
            int(entities[0][0]) if entities else 0,
            int(relations[0][0]) if relations else 0,
        )

    def top_entity_keys(self, limit: int, *, search: str = "") -> list[str]:
        """Most-mentioned entity keys, optionally filtered by a name fragment."""
        if limit <= 0:
            return []
        params: list[object] = [self._kb_id]
        where = ""
        fragment = entity_key(search)
        if fragment:
            escaped = fragment.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where = " AND name_key LIKE ? ESCAPE '\\'"
            params.append(f"%{escaped}%")
        params.append(limit)
        rows = self._fetch(
            f"SELECT name_key, COUNT(*) AS mentions FROM {self._entities} "
            f"WHERE kb_id = ?{where} GROUP BY name_key "
            "ORDER BY mentions DESC, name_key LIMIT ?",
            params,
        )
        return [str(row[0]) for row in rows]

    def match_keys(self, text: str) -> list[str]:
        """Entity keys whose name occurs inside *text* (a user query)."""
        haystack = entity_key(text)
        if not haystack:
            return []
        rows = self._fetch(
            f"SELECT DISTINCT name_key FROM {self._entities} "
            "WHERE kb_id = ? AND ? LIKE '%' || name_key || '%'",
            (self._kb_id, haystack),
        )
        # LIKE treats % and _ inside a name as wildcards; confirm the literal match here.
        return [str(row[0]) for row in rows if str(row[0]) in haystack]

    def entities(self, keys: Sequence[str]) -> dict[str, GraphEntity]:
        """Merge per-chunk rows into one entity per key."""
        rows = self._fetch_in(
            f"SELECT name_key, name, type, description FROM {self._entities} "
            "WHERE kb_id = ? AND name_key IN ({keys})",
            keys,
        )
        names: dict[str, Counter[str]] = {}
        types: dict[str, Counter[str]] = {}
        descriptions: dict[str, str] = {}
        mentions: Counter[str] = Counter()
        for key, name, kind, description in rows:
            key = str(key)
            mentions[key] += 1
            names.setdefault(key, Counter())[str(name)] += 1
            if kind:
                types.setdefault(key, Counter())[str(kind)] += 1
            if len(str(description or "")) > len(descriptions.get(key, "")):
                descriptions[key] = str(description)
        return {
            key: GraphEntity(
                key=key,
                name=_most_common(names[key]),
                type=_most_common(types[key]) if key in types else "",
                description=descriptions.get(key, ""),
                mentions=count,
            )
            for key, count in mentions.items()
        }

    def relations_among(self, keys: Sequence[str]) -> list[GraphRelation]:
        """Relations whose two ends are both in *keys*."""
        wanted = set(keys)
        return [
            relation
            for relation in self.relations_of(keys)
            if relation.source in wanted and relation.target in wanted
        ]

    def relations_of(self, keys: Sequence[str]) -> list[GraphRelation]:
        """Relations touching any of *keys*, merged and sorted by weight."""
        rows = self._fetch_in(
            "SELECT source_key, target_key, label, description, strength, doc_id, ordinal "
            f"FROM {self._relations} "
            "WHERE kb_id = ? AND (source_key IN ({keys}) OR target_key IN ({keys}))",
            keys,
            repeat=2,
        )
        weights: dict[tuple[str, str, str], float] = {}
        descriptions: dict[tuple[str, str, str], str] = {}
        chunks: dict[tuple[str, str, str], dict[tuple[str, int], None]] = {}
        for source, target, label, description, strength, doc_id, ordinal in rows:
            ident = (str(source), str(target), str(label))
            ref = (str(doc_id), int(ordinal))
            seen = chunks.setdefault(ident, {})
            if ref in seen:
                continue  # the same row can come back from two key batches
            seen[ref] = None
            weights[ident] = weights.get(ident, 0.0) + float(strength)
            if len(str(description or "")) > len(descriptions.get(ident, "")):
                descriptions[ident] = str(description)
        merged = [
            GraphRelation(
                source=ident[0],
                target=ident[1],
                label=ident[2],
                description=descriptions.get(ident, ""),
                weight=weight,
                chunks=tuple(chunks[ident]),
            )
            for ident, weight in weights.items()
        ]
        return sorted(merged, key=lambda item: (-item.weight, item.source, item.target, item.label))

    def entity_chunks(self, key: str, *, limit: int = 20) -> list[tuple[str, int]]:
        """Chunks that mention one entity, in document order."""
        rows = self._fetch(
            f"SELECT doc_id, ordinal FROM {self._entities} "
            "WHERE kb_id = ? AND name_key = ? ORDER BY doc_id, ordinal LIMIT ?",
            (self._kb_id, key, limit),
        )
        return [(str(doc_id), int(ordinal)) for doc_id, ordinal in rows]


def _most_common(counter: Counter[str]) -> str:
    # Ties resolve by name so the picked spelling does not depend on row order.
    return min(counter.items(), key=lambda item: (-item[1], item[0]))[0]


class SqliteKnowledgeGraphStore(KnowledgeGraphStore):
    """``graph.sqlite`` beside the knowledge base's vector index."""

    def __init__(self, kb_id: str) -> None:
        super().__init__(kb_id)
        self._path = PathLayout.from_env().knowledge_dir / kb_id / "graph.sqlite"

    @property
    def path(self) -> Path:
        return self._path

    def _present(self) -> bool:
        return self._path.is_file()

    def _connect(self) -> Any:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path)
        self._prepare(conn)
        return conn


class PgKnowledgeGraphStore(KnowledgeGraphStore):
    """``public.knowledge_graph_*`` tables shared by every knowledge base."""

    _entities = "public.knowledge_graph_entities"
    _relations = "public.knowledge_graph_relations"
    _documents = "public.knowledge_graph_documents"
    _mark = "%s"

    def __init__(self, kb_id: str, database: DatabaseConfig) -> None:
        super().__init__(kb_id)
        self._conninfo = database.postgresql_conninfo()
        with self._session() as conn:
            self._prepare(conn)

    def _connect(self) -> Any:
        import psycopg

        return psycopg.connect(self._conninfo)
