"""Tests for symlink-tolerant workspace skill discovery."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from octop.infra.skills.workspace_catalog import list_workspace_skill_summaries


@pytest.mark.skipif(os.name != "posix", reason="symlink semantics are POSIX-specific")
def test_list_workspace_skill_summaries_follows_symlinked_skill(tmp_path: Path) -> None:
    outside = tmp_path / "outside-skill"
    outside.mkdir()
    (outside / "SKILL.md").write_text(
        "---\nname: linked-skill\ndescription: via symlink\n---\n",
        encoding="utf-8",
    )

    workspace = tmp_path / "agent"
    skills_dir = workspace / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "linked-skill").symlink_to(outside, target_is_directory=True)

    rows = list_workspace_skill_summaries(workspace, skills_disabled=set())
    assert rows == [
        {
            "slug": "linked-skill",
            "name": "linked-skill",
            "description": "via symlink",
            "enabled": True,
            "kind": "workspace",
        }
    ]
