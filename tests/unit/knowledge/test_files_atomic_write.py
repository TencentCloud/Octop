"""Atomic persistence for knowledge document originals."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.knowledge.files import document_path, write_document


@pytest.fixture(autouse=True)
def octop_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / ".octop"))


def test_failed_swap_keeps_previous_document(monkeypatch: pytest.MonkeyPatch) -> None:
    original = b"# Original\n"
    path = write_document("kb", "doc", "notes.md", original)
    assert path.read_bytes() == original

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated failure during swap")

    monkeypatch.setattr("os.replace", _boom)
    with pytest.raises(OSError, match="simulated failure during swap"):
        write_document("kb", "doc", "notes.md", b"# Edited but never saved\n")

    assert path.read_bytes() == original
    assert [entry.name for entry in path.parent.iterdir()] == [path.name]


def test_write_document_replaces_content() -> None:
    path = document_path("kb", "doc", "notes.md")
    assert write_document("kb", "doc", "notes.md", b"# v1\n").read_bytes() == b"# v1\n"
    assert write_document("kb", "doc", "notes.md", b"# v2\n").read_bytes() == b"# v2\n"
    assert [entry.name for entry in path.parent.iterdir()] == [path.name]
