"""ChromaDB vector index implementation.

Dependency: chromadb >= 0.4
Install: pip install 'octop-memory[chroma]'

ChromaDB characteristics:
- Runs locally in-process, no Docker required
- Data persisted to a local directory
- Suitable for dev/test, and can also be used in production (single machine)
- Built-in sentence-transformers support (optional)

Usage example:
    from octop_memory.storage.vector.chroma import ChromaVectorIndex

    index = ChromaVectorIndex(
        collection_name="my_agent",
        persist_directory="~/.octop-memory/chroma",
    )
    index.ensure_collection(vector_size=1536)
    index.upsert("atom-123", [0.1, 0.2, ...], {"entity_id": "proj-A"})
    atom_ids = index.search([0.1, 0.2, ...], limit=5)
"""

from __future__ import annotations

import logging
import os
from typing import Any

try:
    import chromadb  # type: ignore[import-not-found]

    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False

from octop_memory.storage.driver_errors import VECTOR_ERRORS

logger = logging.getLogger(__name__)


class ChromaVectorIndex:
    """ChromaDB vector index.

    Args:
        collection_name: ChromaDB collection name; recommended to match the Memory namespace.
        persist_directory: data persistence directory. Defaults to ``~/.octop-memory/chroma``.
        host: if using ChromaDB in HTTP server mode, specify the host (persist_directory is
            ignored in this case).
        port: ChromaDB HTTP server port, default 8000.
    """

    def __init__(
        self,
        collection_name: str,
        *,
        persist_directory: str = "~/.octop-memory/chroma",
        host: str | None = None,
        port: int = 8000,
    ) -> None:
        if not _CHROMA_AVAILABLE:
            raise ImportError(
                "ChromaVectorIndex requires chromadb to be installed.\nPlease run: pip install 'octop-memory[chroma]'"
            )

        self._collection_name = collection_name
        self._collection: Any = None  # lazily initialized; only available after ensure_collection

        if host is not None:
            # HTTP client mode (connects to a remote ChromaDB server)
            self._client = chromadb.HttpClient(host=host, port=port)
        else:
            # Local persistent mode (dev / single-machine production)
            expanded = os.path.expanduser(persist_directory)
            os.makedirs(expanded, exist_ok=True)
            self._client = chromadb.PersistentClient(path=expanded)

    # ------------------------------------------------------------------
    # VectorIndex Protocol implementation
    # ------------------------------------------------------------------

    def ensure_collection(self, vector_size: int) -> None:
        """Initialize or fetch the collection (idempotent).

        ChromaDB's get_or_create_collection is itself idempotent; repeated
        calls neither error out nor clear existing data.
        """
        # embedding_function=None tells ChromaDB that we manage vectors ourselves and
        # don't want its built-in embedding
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={
                "hnsw:space": "cosine",  # cosine similarity, suitable for text embeddings
                "vector_size": vector_size,
            },
            embedding_function=None,
        )

    def upsert(
        self,
        atom_id: str,
        embedding: list[float],
        payload: dict[str, object],
    ) -> None:
        """Write or update a single vector record."""
        if self._collection is None:
            raise RuntimeError("Call ensure_collection() first to initialize the collection")

        # ChromaDB metadata only supports str/int/float/bool; filter out unsupported types
        safe_meta = {k: v for k, v in payload.items() if isinstance(v, str | int | float | bool)}

        self._collection.upsert(
            ids=[atom_id],
            embeddings=[embedding],
            metadatas=[safe_meta],
        )

    def search(
        self,
        embedding: list[float],
        *,
        limit: int = 10,
        where: dict[str, object] | None = None,
    ) -> list[str]:
        """Semantic similarity search; returns a list of atom_ids (descending by similarity)."""
        if self._collection is None:
            raise RuntimeError("Call ensure_collection() first to initialize the collection")

        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": limit,
            "include": [],  # only ids are needed, not documents/embeddings/distances
        }
        if where:
            kwargs["where"] = where

        try:
            result = self._collection.query(**kwargs)
        except VECTOR_ERRORS:
            # ChromaDB raises when the collection is empty; degrade to an empty list.
            logger.warning("chroma query failed for %s", self._collection_name, exc_info=True)
            return []

        ids = result.get("ids", [[]])[0]
        return list(ids)

    def delete(self, atom_id: str) -> None:
        """Delete a single vector record."""
        if self._collection is None:
            return
        try:
            self._collection.delete(ids=[atom_id])
        except VECTOR_ERRORS:
            logger.warning("chroma delete failed for %s", atom_id, exc_info=True)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def __repr__(self) -> str:
        return f"ChromaVectorIndex(collection={self._collection_name!r})"


__all__ = ["ChromaVectorIndex"]
