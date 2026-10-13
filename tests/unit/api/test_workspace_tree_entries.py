"""Tree listing entries stay anchored at the directory the caller requested."""

from __future__ import annotations

from octop.api.common.workspace import reanchor_entry_path


def test_root_listing_entry_keeps_basename_only() -> None:
    # Backend leaked a virtual key (root_dir above the workspace).
    assert reanchor_entry_path(".octop/agents/MSPHTQ/agents/", parent=".") == "agents"


def test_subdir_listing_entry_is_prefixed_with_requested_dir() -> None:
    assert (
        reanchor_entry_path(".octop/agents/MSPHTQ/agents/general.md", parent="agents")
        == "agents/general.md"
    )


def test_workspace_relative_entry_is_unchanged() -> None:
    assert reanchor_entry_path("skills/demo", parent="skills") == "skills/demo"
    assert reanchor_entry_path("notes.md", parent=".") == "notes.md"


def test_empty_entry_path_is_dropped_to_parent() -> None:
    assert reanchor_entry_path("", parent="skills") == "skills"


def test_dedupe_tree_rows_drops_parent_and_duplicate_dir_marker() -> None:
    from octop.infra.backend.tree_listing import dedupe_tree_rows

    rows = dedupe_tree_rows(
        [
            {"path": "/.octop", "is_dir": True},
            {"path": "/.octop/", "is_dir": False, "size": 0},
            {"path": "/.octop", "is_dir": True},
            {"path": "/", "is_dir": True},
            {"path": ".", "is_dir": True},
            {"path": "/SOUL.md", "is_dir": False, "size": 12},
        ],
        parent="/",
    )
    paths = [row["path"] for row in rows]
    assert paths == ["/.octop", "/SOUL.md"]
    assert rows[0]["is_dir"] is True


def test_dedupe_tree_rows_drops_self_when_listing_subdir() -> None:
    from octop.infra.backend.tree_listing import dedupe_tree_rows

    rows = dedupe_tree_rows(
        [
            {"path": "skills", "is_dir": True},
            {"path": "skills/demo", "is_dir": True},
        ],
        parent="skills",
    )
    assert [row["path"] for row in rows] == ["skills/demo"]
