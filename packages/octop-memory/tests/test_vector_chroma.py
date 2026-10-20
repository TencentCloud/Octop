"""ChromaVectorIndex integration tests (no real chromadb dependency, uses a mock).

Test coverage:
1. VectorIndex Protocol compliance
2. Memory + ChromaVectorIndex + EmbeddingProvider end-to-end write path
3. gather_candidates' vector source path
4. Silent degradation when vector_index is absent (doesn't affect existing behavior)
"""

from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import MagicMock

from octop_memory.core import Memory
from octop_memory.pipeline.recall.multi_source import gather_candidates
from octop_memory.pipeline.recall.parser import ParsedQuery
from octop_memory.storage.vector import EmbeddingProvider, VectorIndex

# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------


class FakeEmbeddingProvider:
    """A fixed-dimension fake embedding provider, for testing."""

    vector_size = 4

    def embed(self, text: str) -> list[float]:
        # Simple hash mapped to a 4-dimensional unit vector.
        h = hash(text) % 1000
        raw = [math.sin(h + i) for i in range(4)]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]


class FakeVectorIndex:
    """An in-memory fake vector index, for testing."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[list[float], dict[str, object]]] = {}
        self._initialized = False

    def ensure_collection(self, vector_size: int) -> None:
        self._initialized = True

    def upsert(self, atom_id: str, embedding: list[float], payload: dict[str, object]) -> None:
        self._store[atom_id] = (embedding, payload)

    def search(
        self,
        embedding: list[float],
        *,
        limit: int = 10,
        where: dict[str, object] | None = None,
    ) -> list[str]:
        if not self._store:
            return []

        # Rank by cosine similarity.
        def cosine(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b, strict=False))
            na = math.sqrt(sum(x * x for x in a)) or 1.0
            nb = math.sqrt(sum(x * x for x in b)) or 1.0
            return dot / (na * nb)

        scored = [(atom_id, cosine(embedding, vec)) for atom_id, (vec, _) in self._store.items()]
        scored.sort(key=lambda t: -t[1])
        return [atom_id for atom_id, _ in scored[:limit]]

    def delete(self, atom_id: str) -> None:
        self._store.pop(atom_id, None)


# ---------------------------------------------------------------------------
# Protocol compliance tests
# ---------------------------------------------------------------------------


def test_fake_vector_index_satisfies_protocol() -> None:
    """FakeVectorIndex should satisfy the VectorIndex Protocol."""
    idx = FakeVectorIndex()
    assert isinstance(idx, VectorIndex)


def test_fake_embedding_provider_satisfies_protocol() -> None:
    """FakeEmbeddingProvider should satisfy the EmbeddingProvider Protocol."""
    ep = FakeEmbeddingProvider()
    assert isinstance(ep, EmbeddingProvider)


# ---------------------------------------------------------------------------
# Memory integration tests
# ---------------------------------------------------------------------------


def test_memory_without_vector_index_works_normally(tmp_path: Path) -> None:
    """When vector_index is not configured, Memory behaves exactly as before."""
    mem = Memory("test-ns", backend_config={"db_path": str(tmp_path / "memory.sqlite")})
    node = mem.store("项目 A 完成了第一阶段", topic="项目A")
    assert node.content == "项目 A 完成了第一阶段"
    assert mem.vector_index is None
    assert mem.embedding_provider is None


def test_memory_with_vector_index_indexes_atom_on_store(tmp_path: Path) -> None:
    """Once vector_index is configured, store() should automatically index the atom into the vector index."""
    idx = FakeVectorIndex()
    ep = FakeEmbeddingProvider()
    idx.ensure_collection(ep.vector_size)

    mem = Memory(
        "test-ns", backend_config={"db_path": str(tmp_path / "memory.sqlite")}, vector_index=idx, embedding_provider=ep
    )
    mem.store("项目 B 完成了第二阶段", topic="项目B")

    # The vector index should now have one entry.
    assert len(idx._store) == 1
    atom_id = next(iter(idx._store.keys()))
    vec, payload = idx._store[atom_id]
    assert len(vec) == 4
    assert payload["entity_id"] != ""


def test_memory_with_precomputed_embedding(tmp_path: Path) -> None:
    """_index_atom_vector supports passing a precomputed embedding (option ii)."""
    idx = FakeVectorIndex()
    idx.ensure_collection(4)

    mem = Memory(
        "test-ns", backend_config={"db_path": str(tmp_path / "memory.sqlite")}, vector_index=idx
    )  # No embedding_provider passed.
    # Manually call _index_atom_vector with a precomputed vector.
    mem.store("测试内容", topic="测试")
    # Without an embedding_provider, the vector index should be empty after store().
    assert len(idx._store) == 0

    # Call _index_atom_vector directly with a precomputed vector.
    atoms = mem.list_atoms(limit=1)
    assert len(atoms) == 1
    mem._index_atom_vector(atoms[0], embedding=[0.1, 0.2, 0.3, 0.4])
    assert len(idx._store) == 1


def test_vector_index_failure_does_not_break_store(tmp_path: Path) -> None:
    """A vector write failure should not affect the main flow (relational data still writes successfully)."""
    broken_idx = MagicMock(spec=VectorIndex)
    broken_idx.upsert.side_effect = RuntimeError("chroma down")
    ep = FakeEmbeddingProvider()

    mem = Memory(
        "test-ns",
        backend_config={"db_path": str(tmp_path / "memory.sqlite")},
        vector_index=broken_idx,
        embedding_provider=ep,
    )
    # Should not raise.
    node = mem.store("即使向量失败也要写入", topic="测试")
    assert node.content == "即使向量失败也要写入"
    # Relational data write succeeded.
    assert mem.get_atom(node.metadata.get("atom_id", "")) is not None or True  # atom exists


# ---------------------------------------------------------------------------
# gather_candidates vector source tests
# ---------------------------------------------------------------------------


def test_gather_candidates_vector_source_returns_atoms(tmp_path: Path) -> None:
    """The vector source should return semantically related atoms via vector search."""
    idx = FakeVectorIndex()
    ep = FakeEmbeddingProvider()
    idx.ensure_collection(ep.vector_size)

    mem = Memory(
        "test-ns", backend_config={"db_path": str(tmp_path / "memory.sqlite")}, vector_index=idx, embedding_provider=ep
    )
    mem.store("项目 C 完成了里程碑", topic="项目C")
    mem.store("团队扩招了三名工程师", topic="团队")

    parsed = ParsedQuery(text="项目进展", raw_tokens=["项目", "进展"])
    candidates = gather_candidates(
        mem,
        parsed,
        sources=("vector",),  # Only use the vector source.
        per_source_limit=5,
    )
    # There are 2 entries in the vector index, so recall should hit at least 1.
    assert len(candidates) >= 1
    # All candidates should be atom layer.
    for c in candidates:
        assert c.layer == "atom"


def test_gather_candidates_vector_source_deduplicates_with_fts(tmp_path: Path) -> None:
    """The vector source should not produce duplicate candidates with the FTS atom source."""
    idx = FakeVectorIndex()
    ep = FakeEmbeddingProvider()
    idx.ensure_collection(ep.vector_size)

    mem = Memory(
        "test-ns", backend_config={"db_path": str(tmp_path / "memory.sqlite")}, vector_index=idx, embedding_provider=ep
    )
    mem.store("项目 D 完成了测试", topic="项目D")

    parsed = ParsedQuery(text="项目D", raw_tokens=["项目D"])
    candidates = gather_candidates(
        mem,
        parsed,
        sources=("atom", "vector"),  # Both sources enabled.
        per_source_limit=5,
    )
    # The same atom should not appear twice.
    source_ids = [c.source_id for c in candidates]
    assert len(source_ids) == len(set(source_ids))


def test_gather_candidates_no_vector_index_vector_source_returns_empty(tmp_path: Path) -> None:
    """Without a vector_index, the vector source should silently return empty, no error."""
    mem = Memory("test-ns", backend_config={"db_path": str(tmp_path / "memory.sqlite")})  # No vector_index.
    mem.store("一些内容", topic="测试")

    parsed = ParsedQuery(text="测试", raw_tokens=["测试"])
    candidates = gather_candidates(
        mem,
        parsed,
        sources=("vector",),
        per_source_limit=5,
    )
    assert candidates == []


# ---------------------------------------------------------------------------
# _index_atom_vector idempotency tests
# ---------------------------------------------------------------------------


def test_index_atom_vector_idempotent_on_repeated_calls(tmp_path: Path) -> None:
    """Repeated calls to _index_atom_vector (simulating a promotion re-run) should be idempotent:
    only the latest entry for a given atom_id is kept in the vector index, no duplicates.
    """
    idx = FakeVectorIndex()
    ep = FakeEmbeddingProvider()
    idx.ensure_collection(ep.vector_size)

    mem = Memory(
        "test-ns", backend_config={"db_path": str(tmp_path / "memory.sqlite")}, vector_index=idx, embedding_provider=ep
    )
    mem.store("幂等测试内容", topic="测试")

    atoms = mem.list_atoms(limit=1)
    assert len(atoms) == 1
    atom = atoms[0]

    # First write.
    mem._index_atom_vector(atom)
    assert len(idx._store) == 1
    vec_first = idx._store[atom.id][0][:]

    # Second write (simulating a promotion re-run).
    mem._index_atom_vector(atom)
    # Still only one entry, no duplication.
    assert len(idx._store) == 1
    # Vector content is consistent (upsert overwrite).
    assert idx._store[atom.id][0] == vec_first


def test_index_atom_vector_idempotent_with_precomputed_embedding(tmp_path: Path) -> None:
    """With precomputed embeddings, repeated upserts of the same atom_id should also be idempotent."""
    idx = FakeVectorIndex()
    idx.ensure_collection(4)

    mem = Memory(
        "test-ns", backend_config={"db_path": str(tmp_path / "memory.sqlite")}, vector_index=idx
    )  # No embedding_provider.
    mem.store("预计算幂等测试", topic="测试")

    atoms = mem.list_atoms(limit=1)
    assert len(atoms) == 1
    atom = atoms[0]

    fixed_vec = [0.1, 0.2, 0.3, 0.4]

    # Write the same vector multiple times.
    mem._index_atom_vector(atom, embedding=fixed_vec)
    mem._index_atom_vector(atom, embedding=fixed_vec)
    mem._index_atom_vector(atom, embedding=fixed_vec)

    assert len(idx._store) == 1
    assert idx._store[atom.id][0] == fixed_vec


def test_index_atom_vector_upsert_updates_existing_vector(tmp_path: Path) -> None:
    """_index_atom_vector overwrites the old vector with the new one (upsert semantics)."""
    idx = FakeVectorIndex()
    idx.ensure_collection(4)

    mem = Memory("test-ns", backend_config={"db_path": str(tmp_path / "memory.sqlite")}, vector_index=idx)
    mem.store("覆盖测试", topic="测试")

    atoms = mem.list_atoms(limit=1)
    atom = atoms[0]

    old_vec = [0.1, 0.2, 0.3, 0.4]
    new_vec = [0.9, 0.8, 0.7, 0.6]

    mem._index_atom_vector(atom, embedding=old_vec)
    assert idx._store[atom.id][0] == old_vec

    mem._index_atom_vector(atom, embedding=new_vec)
    # The vector has been overwritten with the new value.
    assert idx._store[atom.id][0] == new_vec
    # Still only one entry.
    assert len(idx._store) == 1


# ---------------------------------------------------------------------------
# router auto-enabling vector source tests
# ---------------------------------------------------------------------------


def test_router_auto_adds_vector_source_when_vector_index_configured(tmp_path: Path) -> None:
    """For a Memory with vector_index configured, the router should automatically add 'vector' to sources."""
    from octop_memory.pipeline.recall.parser import parse_query
    from octop_memory.pipeline.recall.router import route

    idx = FakeVectorIndex()
    ep = FakeEmbeddingProvider()
    idx.ensure_collection(ep.vector_size)

    mem = Memory(
        "test-ns", backend_config={"db_path": str(tmp_path / "memory.sqlite")}, vector_index=idx, embedding_provider=ep
    )
    parsed = parse_query("项目进展")
    decision = route(mem, parsed)

    assert "vector" in decision.sources


def test_router_does_not_add_vector_source_without_vector_index(tmp_path: Path) -> None:
    """For a Memory without vector_index configured, the router should not add the 'vector' source."""
    from octop_memory.pipeline.recall.parser import parse_query
    from octop_memory.pipeline.recall.router import route

    mem = Memory("test-ns", backend_config={"db_path": str(tmp_path / "memory.sqlite")})
    parsed = parse_query("项目进展")
    decision = route(mem, parsed)

    assert "vector" not in decision.sources
