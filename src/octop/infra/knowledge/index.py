"""Per-knowledge-base SQLite sidecar vector index."""

from __future__ import annotations

import json
import math
import sqlite3
import struct
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from operator import mul
from pathlib import Path

from octop.infra.utils.paths import PathLayout

try:  # optional accelerator; pure-Python fallback keeps search working without it
    import numpy as _np
except ImportError:  # pragma: no cover - exercised on minimal installs
    _np = None

# Rows per matmul batch on the numpy path; bounds peak memory to batch*dim*8 bytes.
_NUMPY_BATCH_ROWS = 4096


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    doc_id: str
    ordinal: int
    text: str
    score: float
    metadata: dict[str, object]


class KnowledgeIndex:
    """Store chunk embeddings in one local SQLite database per knowledge base."""

    def __init__(self, kb_id: str) -> None:
        self._path = PathLayout.from_env().knowledge_dir / kb_id / "index.sqlite"
        self._initialize()

    @property
    def path(self) -> Path:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    meta_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
                """
            )

    def replace_doc_chunks(
        self,
        doc_id: str,
        texts: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        *,
        metadata: Sequence[dict[str, object]] | None = None,
    ) -> None:
        """Atomically replace all chunks belonging to one document."""
        if len(texts) != len(embeddings):
            raise ValueError("texts and embeddings must have the same length")
        if metadata is not None and len(metadata) != len(texts):
            raise ValueError("metadata and texts must have the same length")
        rows: list[tuple[str, str, int, str, bytes, str]] = []
        for ordinal, (text, embedding) in enumerate(zip(texts, embeddings, strict=True)):
            vector = [float(value) for value in embedding]
            if not vector:
                raise ValueError("embedding cannot be empty")
            meta = metadata[ordinal] if metadata is not None else {}
            rows.append(
                (
                    f"{doc_id}:{ordinal}",
                    doc_id,
                    ordinal,
                    text,
                    struct.pack(f"<{len(vector)}f", *vector),
                    json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
                )
            )
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            conn.executemany(
                "INSERT INTO chunks(chunk_id, doc_id, ordinal, text, embedding, meta_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )

    def delete_doc(self, doc_id: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))

    def search(self, query_vec: Sequence[float], k: int) -> list[Hit]:
        """Return the ``k`` best chunk hits using in-process cosine similarity.

        Scoring only needs the embedding blobs, so chunk text and JSON metadata
        are fetched in a second query limited to the ``k`` winners instead of
        being decoded for every row.
        """
        if k <= 0:
            return []
        query = [float(value) for value in query_vec]
        if not query:
            raise ValueError("query vector cannot be empty")
        query_norm = math.sqrt(sum(value * value for value in query))
        if query_norm == 0:
            raise ValueError("query vector cannot be zero")
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT chunk_id, doc_id, ordinal, embedding FROM chunks"
            ).fetchall()
            if not rows:
                return []
            scores = self._score_rows([row[3] for row in rows], query, query_norm)
            valid = [i for i, score in enumerate(scores) if score != -math.inf]
            ranked = sorted(valid, key=scores.__getitem__, reverse=True)[:k]
            ids = [rows[i][0] for i in ranked]
            placeholders = ", ".join("?" * len(ids))
            payload = {
                r[0]: (r[1], r[2])
                for r in conn.execute(
                    f"SELECT chunk_id, text, meta_json FROM chunks "
                    f"WHERE chunk_id IN ({placeholders})",
                    ids,
                ).fetchall()
            }
        hits: list[Hit] = []
        for i in ranked:
            chunk_id, doc_id, ordinal, _blob = rows[i]
            # A concurrent replace/delete between the two queries can remove a
            # winner; skip it instead of failing the whole search.
            payload_row = payload.get(chunk_id)
            if payload_row is None:
                continue
            text, meta_json = payload_row
            decoded = json.loads(meta_json)
            hits.append(
                Hit(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    ordinal=ordinal,
                    text=text,
                    score=scores[i],
                    metadata=decoded if isinstance(decoded, dict) else {},
                )
            )
        return hits

    def _score_rows(
        self, blobs: Sequence[bytes], query: list[float], query_norm: float
    ) -> list[float]:
        """Cosine score per row; rows with a mismatched dimension are skipped.

        Skipped rows are given ``-inf`` so they can never rank into the top-k
        (matching the previous behaviour of dropping them from the results).
        """
        dim = len(query)
        if _np is not None:
            return self._score_rows_numpy(blobs, query, query_norm, dim)
        scores: list[float] = [-math.inf] * len(blobs)
        for i, blob in enumerate(blobs):
            embedding = struct.unpack(f"<{len(blob) // 4}f", blob)
            if len(embedding) != dim:
                continue
            norm = math.sqrt(sum(map(mul, embedding, embedding)))
            scores[i] = 0.0 if norm == 0 else sum(map(mul, query, embedding)) / (query_norm * norm)
        return scores

    @staticmethod
    def _score_rows_numpy(
        blobs: Sequence[bytes], query: list[float], query_norm: float, dim: int
    ) -> list[float]:
        assert _np is not None
        scores = _np.full(len(blobs), -_np.inf, dtype=_np.float64)
        query_arr = _np.asarray(query, dtype=_np.float64)
        for start in range(0, len(blobs), _NUMPY_BATCH_ROWS):
            batch = blobs[start : start + _NUMPY_BATCH_ROWS]
            valid: list[int] = []
            vectors: list[_np.ndarray] = []
            for offset, blob in enumerate(batch):
                if len(blob) // 4 != dim:
                    continue
                valid.append(offset)
                vectors.append(_np.frombuffer(blob, dtype="<f4").astype(_np.float64))
            if not valid:
                continue
            matrix = _np.vstack(vectors)
            norms = _np.sqrt((matrix * matrix).sum(axis=1))
            dots = matrix @ query_arr
            batch_scores = _np.zeros(len(valid), dtype=_np.float64)
            nonzero = norms != 0
            batch_scores[nonzero] = dots[nonzero] / (query_norm * norms[nonzero])
            scores[start + _np.asarray(valid)] = batch_scores
        return scores.tolist()
