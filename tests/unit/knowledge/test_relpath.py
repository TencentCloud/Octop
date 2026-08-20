from __future__ import annotations

import pytest

from octop.infra.knowledge.relpath import (
    ancestor_dirs,
    normalize_kb_path,
    path_is_direct_child,
)


def test_normalize_kb_path_rejects_parent_segments() -> None:
    assert normalize_kb_path("/a/b/c.md") == "a/b/c.md"
    with pytest.raises(ValueError):
        normalize_kb_path("../secret")


def test_path_helpers() -> None:
    assert ancestor_dirs("notes/law/act.md") == ["notes", "notes/law"]
    assert path_is_direct_child("notes/law", "notes")
    assert not path_is_direct_child("notes/law/act.md", "notes")
