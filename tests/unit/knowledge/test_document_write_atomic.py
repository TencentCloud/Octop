"""A failed document save must not destroy the document that is already there."""

from __future__ import annotations

import os

import pytest

from octop.infra.knowledge import files as knowledge_files


def test_a_failed_save_keeps_the_original_document(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_files, "document_path", lambda kb, doc, name: tmp_path / name)
    path = knowledge_files.write_document("kb", "doc", "notes.md", b"original body")
    assert path.read_bytes() == b"original body"

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        knowledge_files.write_document("kb", "doc", "notes.md", b"new body")

    # write_bytes truncated first, so the original was replaced by b"new" while the
    # caller saw an exception and the row still reported the old size.
    assert path.read_bytes() == b"original body"
    assert list(tmp_path.glob("*.tmp")) == []


def test_a_failed_first_save_leaves_nothing_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_files, "document_path", lambda kb, doc, name: tmp_path / name)

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        knowledge_files.write_document("kb", "doc", "notes.md", b"new body")

    # A partial file here would be an untracked document in the knowledge dir.
    assert list(tmp_path.iterdir()) == []


def test_a_normal_save_still_writes_the_content(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_files, "document_path", lambda kb, doc, name: tmp_path / name)

    path = knowledge_files.write_document("kb", "doc", "notes.md", b"body")

    assert path.read_bytes() == b"body"
