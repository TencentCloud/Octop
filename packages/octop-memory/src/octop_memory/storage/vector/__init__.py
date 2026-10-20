"""Vector-search enhancement layer -- VectorIndex Protocol.

This layer is an **optional enhancement** over the SQLite/Postgres relational backend,
not a replacement. The relational backend remains the source of truth; VectorIndex is
only responsible for semantic similarity search.

Recall flow:
  query -> embed -> VectorIndex.search() -> [atom_id, ...] -> backend.get_atom() -> AtomCard

Write flow:
  After an AtomCard is written to the backend -> VectorIndex.upsert(atom_id, embedding, payload)

Supported implementations (VectorIndex):
  - ChromaVectorIndex  (chromadb)
  - QdrantVectorIndex  (qdrant-client)
  - FaissVectorIndex   (faiss-cpu, not yet implemented)

Built-in EmbeddingProvider (storage/vector/embeddings.py):
  - OpenAIEmbeddingProvider          -- OpenAI / compatible endpoints, no extra deps
  - OllamaEmbeddingProvider          -- local Ollama, no extra deps
  - SentenceTransformerEmbeddingProvider -- local model, requires pip install 'octop-memory[embeddings]'
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """A provider that converts text into a vector.

    Can be any implementation, e.g. OpenAI text-embedding-3-small, a local
    sentence-transformers model, etc. Callers may also pass a precomputed
    embedding directly, in which case no EmbeddingProvider is needed.
    """

    def embed(self, text: str) -> list[float]:
        """Convert a single piece of text into an embedding vector."""
        ...

    @property
    def vector_size(self) -> int:
        """Return the vector dimension, used to initialize the collection."""
        ...


@runtime_checkable
class VectorIndex(Protocol):
    """The generic protocol for a vector search index.

    Only 4 methods, intentionally kept minimal:
    - upsert: write/update a single vector
    - search: semantic similarity search, returns a list of atom_ids
    - delete: delete a single vector
    - ensure_collection: initialize the collection (idempotent)

    Concrete implementations: ChromaVectorIndex, QdrantVectorIndex, etc.
    """

    def ensure_collection(self, vector_size: int) -> None:
        """Initialize the collection (idempotent, safe to call repeatedly)."""
        ...

    def upsert(
        self,
        atom_id: str,
        embedding: list[float],
        payload: dict[str, object],
    ) -> None:
        """Write or update a single vector record.

        Args:
            atom_id: corresponds to AtomCard.id, used as the vector's unique id.
            embedding: the vector; its dimension must match the one used in ensure_collection.
            payload: additional metadata (entity_id, occurred_at, etc.), used for filtering.
        """
        ...

    def search(
        self,
        embedding: list[float],
        *,
        limit: int = 10,
        where: dict[str, object] | None = None,
    ) -> list[str]:
        """Semantic similarity search; returns the most similar atom_ids (descending by similarity).

        Args:
            embedding: the query vector.
            limit: maximum number of results to return.
            where: optional metadata filter condition (format determined by the concrete implementation).

        Returns:
            A list of atom_ids, sorted descending by similarity.
        """
        ...

    def delete(self, atom_id: str) -> None:
        """Delete a single vector record (called when an atom is garbage-collected)."""
        ...


__all__ = ["EmbeddingProvider", "VectorIndex"]
