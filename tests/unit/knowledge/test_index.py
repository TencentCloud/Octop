"""Unit tests for per-knowledge-base sidecar indexes."""

from __future__ import annotations

import math
import struct

import pytest

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


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_embeddings_cannot_replace_valid_chunks(tmp_path, monkeypatch, value) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    index = KnowledgeIndex("kb")
    index.replace_doc_chunks("doc", ["original"], [[1.0, 0.0]])
    with pytest.raises(ValueError, match="finite"):
        index.replace_doc_chunks("doc", ["valid", "bad"], [[1.0, 0.0], [value, 1.0]])
    hits = index.search([1.0, 0.0], 10)
    assert [hit.text for hit in hits] == ["original"]
    assert hits[0].score == 1.0


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, 1e308])
def test_nonfinite_query_is_rejected(tmp_path, monkeypatch, value) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    index = KnowledgeIndex("kb")
    index.replace_doc_chunks("doc", ["original"], [[1.0, 0.0]])
    with pytest.raises(ValueError, match="finite"):
        index.search([value, 1.0], 10)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_legacy_nonfinite_chunks_do_not_poison_healthy_hits(tmp_path, monkeypatch, value) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    index = KnowledgeIndex("kb")
    index.replace_doc_chunks("good", ["healthy"], [[1.0, 0.0]])
    conn = index._connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                ("bad:0", "bad", 0, "legacy bad", struct.pack("<2f", value, 1.0), "{}"),
            )
    finally:
        conn.close()
    hits = index.search([1.0, 0.0], 10)
    assert [hit.text for hit in hits] == ["healthy"]
    assert math.isfinite(hits[0].score)
