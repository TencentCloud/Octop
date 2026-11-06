"""pgvector chunk index for one knowledge base.

``CREATE EXTENSION vector`` is an operator step (see
``docker/postgres/init-vector.sql`` and ADR 002). This module only creates
``public.knowledge_chunks`` once the ``vector`` type exists.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from octop.config import DatabaseConfig
from octop.infra.db.file_store import KNOWLEDGE_CHUNKS, adopt_legacy_content_tables
from octop.infra.knowledge.index import Hit

_TABLE = f"public.{KNOWLEDGE_CHUNKS}"


def _vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(format(float(value), ".8g") for value in values) + "]"


class PgVectorKnowledgeIndex:
    """Cosine search over ``public.knowledge_chunks`` for one knowledge base."""

    def __init__(self, kb_id: str, database: DatabaseConfig) -> None:
        self._kb_id = kb_id
        self._database = database
        self._conninfo = database.postgresql_conninfo()
        self._ensure_schema()

    def _connect(self) -> Any:
        import psycopg

        return psycopg.connect(self._conninfo)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            present = conn.execute("SELECT 1 FROM pg_type WHERE typname = 'vector'").fetchone()
            if present is None:
                raise RuntimeError(
                    "pgvector is not installed on this PostgreSQL. "
                    "Run CREATE EXTENSION vector (docker/postgres/init-vector.sql) "
                    "before using knowledge search with database.driver=postgresql."
                )
            adopt_legacy_content_tables(self._database)
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_TABLE} (
                    kb_id TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    embedding vector NOT NULL,
                    meta_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    PRIMARY KEY (kb_id, chunk_id)
                )
                """
            )
            conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_doc
                ON {_TABLE} (kb_id, doc_id)
                """
            )
            conn.commit()

    def replace_doc_chunks(
        self,
        doc_id: str,
        texts: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        *,
        metadata: Sequence[dict[str, object]] | None = None,
    ) -> None:
        if len(texts) != len(embeddings):
            raise ValueError("texts and embeddings must have the same length")
        if metadata is not None and len(metadata) != len(texts):
            raise ValueError("metadata and texts must have the same length")
        from psycopg.types.json import Jsonb

        rows: list[tuple[object, ...]] = []
        for ordinal, (text, embedding) in enumerate(zip(texts, embeddings, strict=True)):
            vector = [float(value) for value in embedding]
            if not vector:
                raise ValueError("embedding cannot be empty")
            meta = metadata[ordinal] if metadata is not None else {}
            rows.append(
                (
                    self._kb_id,
                    f"{doc_id}:{ordinal}",
                    doc_id,
                    ordinal,
                    text,
                    _vector_literal(vector),
                    Jsonb(meta),
                )
            )
        with self._connect() as conn:
            conn.execute(
                f"DELETE FROM {_TABLE} WHERE kb_id = %s AND doc_id = %s",
                (self._kb_id, doc_id),
            )
            if rows:
                with conn.cursor() as cur:
                    cur.executemany(
                        f"""
                        INSERT INTO {_TABLE}
                            (kb_id, chunk_id, doc_id, ordinal, text, embedding, meta_json)
                        VALUES (%s, %s, %s, %s, %s, %s::vector, %s)
                        """,
                        rows,
                    )
            conn.commit()

    def list_doc_chunks(self, doc_id: str) -> list[tuple[int, str]]:
        """Return stored slices for one document, in ordinal order."""
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT ordinal, text FROM {_TABLE}
                WHERE kb_id = %s AND doc_id = %s
                ORDER BY ordinal
                """,
                (self._kb_id, doc_id),
            ).fetchall()
        return [(int(ordinal), str(text)) for ordinal, text in rows]

    def delete_doc(self, doc_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                f"DELETE FROM {_TABLE} WHERE kb_id = %s AND doc_id = %s",
                (self._kb_id, doc_id),
            )
            conn.commit()

    def delete_kb(self) -> None:
        with self._connect() as conn:
            conn.execute(
                f"DELETE FROM {_TABLE} WHERE kb_id = %s",
                (self._kb_id,),
            )
            conn.commit()

    def search(self, query_vec: Sequence[float], k: int) -> list[Hit]:
        if k <= 0:
            return []
        query = [float(value) for value in query_vec]
        if not query:
            raise ValueError("query vector cannot be empty")
        if all(value == 0 for value in query):
            raise ValueError("query vector cannot be zero")
        literal = _vector_literal(query)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT chunk_id, doc_id, ordinal, text, meta_json,
                       1 - (embedding <=> %s::vector) AS score
                FROM {_TABLE}
                WHERE kb_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (literal, self._kb_id, literal, k),
            ).fetchall()
        hits: list[Hit] = []
        for chunk_id, doc_id, ordinal, text, meta_json, score in rows:
            decoded = meta_json
            if isinstance(decoded, str):
                decoded = json.loads(decoded)
            hits.append(
                Hit(
                    chunk_id=str(chunk_id),
                    doc_id=str(doc_id),
                    ordinal=int(ordinal),
                    text=str(text),
                    score=float(score),
                    metadata=decoded if isinstance(decoded, dict) else {},
                )
            )
        return hits
