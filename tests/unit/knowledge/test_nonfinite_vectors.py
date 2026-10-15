"""Non-finite embeddings and queries must be rejected, not stored."""

from __future__ import annotations

import math

import pytest

from octop.infra.knowledge.index import KnowledgeIndex

QUERY = [1.0, 0.0]


def _index(tmp_path) -> KnowledgeIndex:
    return KnowledgeIndex(str(tmp_path / "index.sqlite"))


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_embeddings_are_rejected(bad, tmp_path):
    index = _index(tmp_path)
    index.replace_doc_chunks("doc", ["good"], [[0.5, 0.5]])

    with pytest.raises(ValueError):
        index.replace_doc_chunks("doc", ["bad"], [[bad, 1.0]])

    # The previous chunks must survive a rejected replacement.
    assert [hit.doc_id for hit in index.search(QUERY, k=1)] == ["doc"]


@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_non_finite_queries_are_rejected(bad, tmp_path):
    index = _index(tmp_path)
    index.replace_doc_chunks("doc", ["good"], [[0.5, 0.5]])

    with pytest.raises(ValueError):
        index.search([bad, 0.0], k=1)


def test_stored_non_finite_rows_are_skipped(tmp_path):
    index = _index(tmp_path)
    index.replace_doc_chunks("doc", ["good"], [[0.5, 0.5]])
    # Simulate a row written before the validation existed.
    with index._connect() as conn:
        conn.execute(
            "UPDATE chunks SET embedding = ? WHERE chunk_id = ?",
            (__import__("struct").pack("<2f", math.inf, math.inf), "doc:0"),
        )

    assert index.search(QUERY, k=1) == []
