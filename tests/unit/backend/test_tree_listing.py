"""Tests for single-level storage / workspace tree dedupe."""

from __future__ import annotations

from octop.infra.backend.tree_listing import dedupe_tree_rows, is_listing_self


def test_is_listing_self_root() -> None:
    assert is_listing_self("/", parent="/")
    assert is_listing_self(".", parent="/")
    assert not is_listing_self("a.txt", parent="/")


def test_dedupe_tree_rows_drops_self_and_merges() -> None:
    rows = [
        {"path": "/", "is_dir": True},
        {"path": "a.txt", "is_dir": False, "size": 1},
        {"path": "a.txt/", "is_dir": True},
        {"path": "sub", "is_dir": True},
    ]
    out = dedupe_tree_rows(rows, parent="/")
    assert [row["path"] for row in out] == ["a.txt", "sub"]
    assert out[0]["is_dir"] is True
