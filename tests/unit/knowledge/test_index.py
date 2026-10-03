"""Unit tests for per-knowledge-base sidecar indexes."""

from __future__ import annotations

import math
import random
import struct

import pytest

import octop.infra.knowledge.index as index_module
from octop.infra.knowledge.index import KnowledgeIndex


def test_index_replaces_document_chunks_and_returns_cosine_top_k(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    index = KnowledgeIndex("kb-1")

    index.replace_doc_chunks(
        "doc-1",
        ["first", "second"],
        [[1.0, 0.0], [0.0, 1.0]],
        metadata=[{"page": 1}, {"page": 2}],
    )
    index.replace_doc_chunks("doc-2", ["third"], [[0.8, 0.2]])

    hits = index.search([1.0, 0.0], k=2)

    assert [hit.text for hit in hits] == ["first", "third"]
    assert hits[0].doc_id == "doc-1"
    assert hits[0].ordinal == 0
    assert hits[0].metadata == {"page": 1}

    index.replace_doc_chunks("doc-1", ["replacement"], [[0.0, 1.0]])
    assert [hit.text for hit in index.search([1.0, 0.0], k=5)] == ["third", "replacement"]

    index.delete_doc("doc-2")
    assert [hit.doc_id for hit in index.search([1.0, 0.0], k=5)] == ["doc-1"]


def _reference_search(index: KnowledgeIndex, query: list[float], k: int) -> list[tuple]:
    """The pre-optimization single-pass behaviour, kept as the oracle."""
    with index_module.closing(index._connect()) as conn:
        raw = conn.execute(
            "SELECT chunk_id, doc_id, ordinal, text, embedding, meta_json FROM chunks"
        ).fetchall()
    query_norm = math.sqrt(sum(value * value for value in query))
    scored = []
    for chunk_id, doc_id, ordinal, text, blob, meta_json in raw:
        embedding = struct.unpack(f"<{len(blob) // 4}f", blob)
        if len(embedding) != len(query):
            continue
        norm = math.sqrt(sum(value * value for value in embedding))
        score = (
            0.0
            if norm == 0
            else sum(a * b for a, b in zip(query, embedding, strict=True)) / (query_norm * norm)
        )
        scored.append((score, (chunk_id, doc_id, ordinal, text, meta_json)))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:k]


@pytest.mark.parametrize("force_fallback", [False, True])
def test_search_matches_reference_implementation(tmp_path, monkeypatch, force_fallback) -> None:
    """Ranking must agree with the previous single-pass scan on random data."""
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    if force_fallback:
        monkeypatch.setattr(index_module, "_np", None)
    index = KnowledgeIndex("kb-ref")
    rnd = random.Random(2026)
    dim = 64
    texts, embeddings, metas = [], [], []
    for i in range(400):
        texts.append(f"chunk-{i}")
        embeddings.append([rnd.gauss(0, 1) for _ in range(dim)])
        metas.append({"i": i})
    index.replace_doc_chunks("doc-0", texts, embeddings, metadata=metas)
    # A chunk with a mismatched dimension and a zero vector: neither may rank
    # above valid chunks, and the mismatched one must never be returned.
    with index_module.closing(index._connect()) as conn, conn:
        conn.execute(
            "INSERT INTO chunks(chunk_id, doc_id, ordinal, text, embedding, meta_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "doc-0:bad",
                "doc-0",
                400,
                "bad-dim",
                struct.pack("<2f", 1.0, 2.0),
                "{}",
            ),
        )
        conn.execute(
            "INSERT INTO chunks(chunk_id, doc_id, ordinal, text, embedding, meta_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "doc-0:zero",
                "doc-0",
                401,
                "zero",
                struct.pack(f"<{dim}f", *([0.0] * dim)),
                "{}",
            ),
        )

    query = [rnd.gauss(0, 1) for _ in range(dim)]
    hits = index.search(query, k=50)
    reference = _reference_search(index, query, k=50)

    assert [hit.chunk_id for hit in hits] == [row[1][0] for row in reference]
    for hit, (score, _meta) in zip(hits, reference, strict=True):
        assert hit.score == pytest.approx(score, abs=1e-9)
        assert hit.metadata is not None
    assert all(hit.text != "bad-dim" for hit in hits)
    zero_hits = [hit for hit in hits if hit.text == "zero"]
    if zero_hits:
        assert zero_hits[0].score == 0.0


def test_search_dim_mismatch_rows_do_not_fill_top_k(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    index = KnowledgeIndex("kb-dim")
    index.replace_doc_chunks("doc-1", ["only"], [[1.0, 0.0]])
    with index_module.closing(index._connect()) as conn, conn:
        conn.execute(
            "INSERT INTO chunks(chunk_id, doc_id, ordinal, text, embedding, meta_json) "
            "VALUES ('doc-9:0', 'doc-9', 0, 'alien', X'00000000', '{}')"
        )
    hits = index.search([1.0, 0.0], k=5)
    assert [hit.text for hit in hits] == ["only"]


def test_search_ties_keep_row_order(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    index = KnowledgeIndex("kb-ties")
    index.replace_doc_chunks("doc-1", ["a", "b", "c"], [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]])
    hits = index.search([1.0, 0.0], k=3)
    assert [hit.text for hit in hits] == ["a", "b", "c"]
    assert len({hit.score for hit in hits}) == 1


def test_search_zero_query_and_non_positive_k(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    index = KnowledgeIndex("kb-empty")
    index.replace_doc_chunks("doc-1", ["a"], [[1.0, 0.0]])
    assert index.search([1.0, 0.0], k=0) == []
    with pytest.raises(ValueError, match="zero"):
        index.search([0.0, 0.0], k=3)
    with pytest.raises(ValueError, match="empty"):
        index.search([], k=3)
