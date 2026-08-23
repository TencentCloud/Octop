"""Unit tests for knowledge citation markers."""

from __future__ import annotations

from types import SimpleNamespace

from octop.infra.knowledge.citations import (
    CITATIONS_MARKER_PREFIX,
    append_citations_marker,
    citations_from_ranked,
    strip_citations_marker,
)


def test_citations_from_ranked_dedupes_documents() -> None:
    base = SimpleNamespace(id="kb1", name="Policies")
    doc_a = SimpleNamespace(id="d1", filename="a.md")
    doc_b = SimpleNamespace(id="d2", filename="b.md")
    hit = SimpleNamespace()
    ranked = [
        (base, hit, doc_a),
        (base, hit, doc_a),
        (base, hit, doc_b),
    ]
    assert citations_from_ranked(ranked) == [
        {"kb_id": "kb1", "kb_name": "Policies", "doc_id": "d1", "filename": "a.md"},
        {"kb_id": "kb1", "kb_name": "Policies", "doc_id": "d2", "filename": "b.md"},
    ]


def test_append_citations_marker() -> None:
    text = append_citations_marker(
        "passages here",
        [{"kb_id": "kb", "kb_name": "KB", "doc_id": "d1", "filename": "doc.md"}],
    )
    assert text.startswith("passages here\n\n" + CITATIONS_MARKER_PREFIX)
    assert '"filename":"doc.md"' in text
    assert text.endswith("-->")


def test_append_citations_marker_skips_empty() -> None:
    assert (
        append_citations_marker(
            "", [{"kb_id": "k", "kb_name": "n", "doc_id": "d", "filename": "f"}]
        )
        == ""
    )
    assert append_citations_marker("text", []) == "text"


def test_strip_citations_marker() -> None:
    raw = append_citations_marker(
        "passages here",
        [{"kb_id": "kb", "kb_name": "KB", "doc_id": "d1", "filename": "doc.md"}],
    )
    assert strip_citations_marker(raw) == "passages here"
    assert strip_citations_marker("plain") == "plain"
