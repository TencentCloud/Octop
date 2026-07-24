"""Tests for source-neutral skill package normalization."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from octop.infra.agents import skill_packages


def test_resolve_package_from_an_independent_market() -> None:
    package = skill_packages.resolve_skill_package(
        slug="other-market-skill",
        files=[
            ("SKILL.md", b"---\nname: other-market-skill\n---\n"),
            ("assets/icon.bin", b"\x00\x01"),
        ],
        source="other-market",
        source_url="https://market.example/skills/other-market-skill",
    )

    assert package.source == "other-market"
    assert package.source_url == "https://market.example/skills/other-market-skill"
    assert package.workspace_uploads() == [
        (
            "skills/other-market-skill/SKILL.md",
            b"---\nname: other-market-skill\n---\n",
        ),
        ("skills/other-market-skill/assets/icon.bin", b"\x00\x01"),
    ]


def test_resolve_legacy_import_uploads_uses_the_same_pipeline() -> None:
    package = skill_packages.resolve_workspace_uploads(
        slug="github-skill",
        uploads=[
            ("skills/github-skill/SKILL.md", b"# skill"),
            ("skills/github-skill/references/doc.md", b"# doc"),
        ],
        source="url",
        source_url="https://github.com/example/repo",
    )

    assert dict(package.files) == {
        "SKILL.md": b"# skill",
        "references/doc.md": b"# doc",
    }


@pytest.mark.parametrize(
    "path",
    [
        "../escape",
        "/absolute",
        "nested/../../escape",
        "nested\\escape",
        "C:/windows",
    ],
)
def test_resolve_package_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(skill_packages.SkillPackageError):
        skill_packages.resolve_skill_package(
            slug="safe",
            files=[("SKILL.md", b"# skill"), (path, b"unsafe")],
            source="test",
        )


def test_resolve_import_rejects_files_outside_the_skill_root() -> None:
    with pytest.raises(skill_packages.SkillPackageError, match="outside"):
        skill_packages.resolve_workspace_uploads(
            slug="safe",
            uploads=[
                ("skills/safe/SKILL.md", b"# skill"),
                ("skills/other/escape.md", b"unsafe"),
            ],
            source="url",
        )


def test_resolve_package_enforces_shared_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skill_packages, "MAX_SKILL_BYTES", 4)

    with pytest.raises(skill_packages.SkillPackageTooLarge, match="64 MB"):
        skill_packages.resolve_skill_package(
            slug="large",
            files=[("SKILL.md", b"12345")],
            source="test",
        )


def test_resolve_package_requires_utf8_manifest() -> None:
    with pytest.raises(skill_packages.SkillPackageError, match="UTF-8"):
        skill_packages.resolve_skill_package(
            slug="binary-manifest",
            files=[("SKILL.md", b"\xff\xfe")],
            source="test",
        )


@pytest.mark.skipif(os.name != "posix", reason="symlink semantics are POSIX-specific")
def test_read_skill_directory_rejects_symlink(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("# skill", encoding="utf-8")
    (tmp_path / "target").write_text("target", encoding="utf-8")
    (tmp_path / "link").symlink_to(tmp_path / "target")

    with pytest.raises(skill_packages.SkillPackageError, match="file type"):
        skill_packages.read_skill_directory(tmp_path)


def test_read_cli_skill_install_accepts_files_at_install_root(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("# root skill", encoding="utf-8")

    assert skill_packages.read_cli_skill_install(tmp_path) == [("SKILL.md", b"# root skill")]


def test_read_cli_skill_install_discovers_single_wrapper_directory(tmp_path: Path) -> None:
    wrapper = tmp_path / "cli-generated-directory"
    wrapper.mkdir()
    (wrapper / "SKILL.md").write_text("# wrapped skill", encoding="utf-8")

    assert skill_packages.read_cli_skill_install(tmp_path) == [("SKILL.md", b"# wrapped skill")]


def test_read_cli_skill_install_rejects_ambiguous_packages(tmp_path: Path) -> None:
    for name in ("one", "two"):
        wrapper = tmp_path / name
        wrapper.mkdir()
        (wrapper / "SKILL.md").write_text(f"# {name}", encoding="utf-8")

    with pytest.raises(skill_packages.SkillPackageError, match="multiple"):
        skill_packages.read_cli_skill_install(tmp_path)


@pytest.mark.skipif(os.name != "posix", reason="symlink semantics are POSIX-specific")
def test_read_cli_skill_install_does_not_follow_wrapper_symlink(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-skill"
    outside.mkdir()
    (outside / "SKILL.md").write_text("# outside", encoding="utf-8")
    (tmp_path / "wrapper").symlink_to(outside, target_is_directory=True)

    with pytest.raises(skill_packages.SkillPackageError, match="did not produce"):
        skill_packages.read_cli_skill_install(tmp_path)
