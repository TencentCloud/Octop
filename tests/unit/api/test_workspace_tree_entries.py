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
