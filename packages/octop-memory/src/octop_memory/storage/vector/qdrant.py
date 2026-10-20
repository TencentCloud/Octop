"""Qdrant vector index implementation.

Dependency: qdrant-client >= 1.7
Install: pip install 'octop-memory[qdrant]'

Qdrant characteristics:
- Supports local in-memory mode (dev/test, no Docker required)
- Supports local persistent mode (single-machine production)
- Supports remote HTTP/gRPC mode (distributed production)
- High-performance HNSW index, suitable for large-scale vector search

Usage example:
    from octop_memory.storage.vector.qdrant import QdrantVectorIndex

    # Local in-memory mode (dev/test)
    index = QdrantVectorIndex(collection_name="my_agent")
    index.ensure_collection(vector_size=1536)
    index.upsert("atom-123", [0.1, 0.2, ...], {"entity_id": "proj-A"})
    atom_ids = index.search([0.1, 0.2, ...], limit=5)

    # Remote mode (production)
    index = QdrantVectorIndex(
        collection_name="my_agent",
        url="http://localhost:6333",
    )
"""

from __future__ import annotations

import logging
import os
from typing import Any

try:
    from qdrant_client import QdrantClient  # type: ignore[import-not-found]
    from qdrant_client.http import models as qmodels  # type: ignore[import-not-found]

    _QDRANT_AVAILABLE = True
except ImportError:
    _QDRANT_AVAILABLE = False

from octop_memory.storage.driver_errors import VECTOR_ERRORS

logger = logging.getLogger(__name__)


class QdrantVectorIndex:
    """Qdrant vector index.

    Args:
        collection_name: Qdrant collection name; recommended to match the Memory namespace.
        url: Qdrant service address (e.g. ``http://localhost:6333``).
             If None, uses local in-memory mode (dev/test).
        api_key: API key required by Qdrant Cloud or services that require authentication.
        path: local persistence directory. If url is also specified, url takes priority.
              If both url and path are None, in-memory mode is used.
        prefer_grpc: whether to prefer a gRPC connection (more efficient in remote mode).
    """

    def __init__(
        self,
        collection_name: str,
        *,
        url: str | None = None,
        api_key: str | None = None,
        path: str | None = None,
        prefer_grpc: bool = False,
    ) -> None:
        if not _QDRANT_AVAILABLE:
            raise ImportError(
                "QdrantVectorIndex requires qdrant-client to be installed.\n"
                "Please run: pip install 'octop-memory[qdrant]'"
            )

        self._collection_name = collection_name
        self._vector_size: int | None = None  # only known after ensure_collection

        if url is not None:
            # Remote HTTP/gRPC mode
            self._client: Any = QdrantClient(
                url=url,
                api_key=api_key,
                prefer_grpc=prefer_grpc,
            )
        elif path is not None:
            # Local persistent mode
            expanded = os.path.expanduser(path)
            os.makedirs(expanded, exist_ok=True)
            self._client = QdrantClient(path=expanded)
        else:
            # In-memory mode (dev/test; data disappears when the process exits)
            self._client = QdrantClient(":memory:")

    # ------------------------------------------------------------------
    # VectorIndex Protocol implementation
    # ------------------------------------------------------------------

    def ensure_collection(self, vector_size: int) -> None:
        """Initialize or fetch the collection (idempotent).

        If the collection already exists with a matching dimension, it is reused as-is;
        if it doesn't exist, a new collection is created (cosine distance).
        """
        self._vector_size = vector_size

        existing = self._client.get_collections().collections
        existing_names = {c.name for c in existing}

        if self._collection_name not in existing_names:
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=qmodels.VectorParams(
                    size=vector_size,
                    distance=qmodels.Distance.COSINE,
                ),
            )

    def upsert(
        self,
        atom_id: str,
        embedding: list[float],
        payload: dict[str, object],
    ) -> None:
        """Write or update a single vector record."""
        # Qdrant point ids only support unsigned int or UUID strings;
        # atom_id is already in UUID format so it's used as-is
        safe_payload = {k: v for k, v in payload.items() if isinstance(v, str | int | float | bool)}
        self._client.upsert(
            collection_name=self._collection_name,
            points=[
                qmodels.PointStruct(
                    id=atom_id,
                    vector=embedding,
                    payload=safe_payload,
                )
            ],
        )

    def search(
        self,
        embedding: list[float],
        *,
        limit: int = 10,
        where: dict[str, object] | None = None,
    ) -> list[str]:
        """Semantic similarity search; returns a list of atom_ids (descending by similarity)."""
        query_filter: Any = None
        if where:
            # Convert a simple {key: value} mapping into a Qdrant Filter
            conditions = [
                qmodels.FieldCondition(
                    key=k,
                    match=qmodels.MatchValue(value=v),
                )
                for k, v in where.items()
                if isinstance(v, str | int | float | bool)
            ]
            if conditions:
                query_filter = qmodels.Filter(must=conditions)

        try:
            results = self._client.search(
                collection_name=self._collection_name,
                query_vector=embedding,
                limit=limit,
                query_filter=query_filter,
                with_payload=False,
                with_vectors=False,
            )
        except VECTOR_ERRORS:
            # Collection is empty or the client failed; degrade to an empty list.
            logger.warning("qdrant search failed for %s", self._collection_name, exc_info=True)
            return []

        return [str(hit.id) for hit in results]

    def delete(self, atom_id: str) -> None:
        """Delete a single vector record."""
        try:
            self._client.delete(
                collection_name=self._collection_name,
                points_selector=qmodels.PointIdsList(points=[atom_id]),
            )
        except VECTOR_ERRORS:
            logger.warning("qdrant delete failed for %s", atom_id, exc_info=True)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def __repr__(self) -> str:
        return f"QdrantVectorIndex(collection={self._collection_name!r})"


__all__ = ["QdrantVectorIndex"]
