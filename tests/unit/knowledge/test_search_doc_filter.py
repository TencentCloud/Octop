"""Stale chunks must not consume the top-k budget of ready documents."""

from __future__ import annotations

from octop.infra.knowledge.index import KnowledgeIndex

QUERY = [1.0, 0.0]


def _index(tmp_path) -> KnowledgeIndex:
    index = KnowledgeIndex(str(tmp_path / "index.sqlite"))
    index.replace_doc_chunks("ready-doc", ["close match"], [[0.9, 0.1]])
    index.replace_doc_chunks("stale-doc", ["stale but closer"], [[1.0, 0.0]])
    return index


def test_without_a_filter_the_stale_chunk_wins(tmp_path):
    """Control: this is the behaviour the issue reports."""
    hits = _index(tmp_path).search(QUERY, k=1)

    assert [hit.doc_id for hit in hits] == ["stale-doc"]


def test_the_doc_filter_excludes_stale_chunks_before_truncation(tmp_path):
    index = _index(tmp_path)

    hits = index.search(QUERY, k=1, doc_ids={"ready-doc"})

    assert [hit.doc_id for hit in hits] == ["ready-doc"]


def test_the_filter_still_ranks_by_similarity(tmp_path):
    index = _index(tmp_path)

    hits = index.search(QUERY, k=2, doc_ids={"ready-doc", "stale-doc"})

    assert [hit.doc_id for hit in hits] == ["stale-doc", "ready-doc"]
