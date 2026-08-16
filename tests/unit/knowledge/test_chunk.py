"""Unit tests for document chunking."""

from __future__ import annotations

import pytest

from octop.infra.knowledge.chunk import chunk_text


def test_chunk_text_preserves_content_with_configured_overlap() -> None:
    chunks = chunk_text("abcdefghij", size=4, overlap=1)

    assert chunks == ["abcd", "defg", "ghij"]


def test_chunk_text_strips_empty_content_and_rejects_invalid_window() -> None:
    assert chunk_text(" \n\t ") == []
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("text", size=4, overlap=4)
