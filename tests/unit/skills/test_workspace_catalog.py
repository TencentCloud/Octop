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


def test_list_workspace_skill_summaries_repairs_known_utf8_corruption(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "agent"
    skill_dir = workspace / "skills" / "humanizer"
    skill_dir.mkdir(parents=True)
    corrupted = (
        "---\nname: humanizer\ndescription: copy\n---\n每句 ".encode()
        + b"\xe2j$"
        + "15 字\n".encode()
    )
    (skill_dir / "SKILL.md").write_bytes(corrupted)

    rows = list_workspace_skill_summaries(workspace, skills_disabled=set())

    assert [row["slug"] for row in rows] == ["humanizer"]
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "≤15" in text


def test_list_workspace_skill_summaries_skips_unrepairable_utf8(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    workspace = tmp_path / "agent"
    good = workspace / "skills" / "good"
    bad = workspace / "skills" / "bad"
    good.mkdir(parents=True)
    bad.mkdir(parents=True)
    (good / "SKILL.md").write_text(
        "---\nname: good\ndescription: ok\n---\n",
        encoding="utf-8",
    )
    (bad / "SKILL.md").write_bytes(b"---\nname: bad\n---\n\xff\xfe broken")

    with caplog.at_level("WARNING"):
        rows = list_workspace_skill_summaries(workspace, skills_disabled=set())

    assert [row["slug"] for row in rows] == ["bad", "good"]
    corrupt = next(row for row in rows if row["slug"] == "bad")
    assert corrupt["corrupt"] is True
    assert corrupt["error"] == "invalid_utf8"
    assert corrupt["enabled"] is False
    assert any("not valid UTF-8" in record.message for record in caplog.records)
