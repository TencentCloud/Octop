"""Unit tests for shared skill install target pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from octop.infra.skills.install import (
    SkillAlreadyExistsError,
    SkillInstallTarget,
    commit_skill_install,
    prepare_skillhub_package,
)
from octop.infra.skills.skill_packages import ResolvedSkillPackage, resolve_skill_package


@dataclass
class FakeTarget:
    existing: set[str] = field(default_factory=set)
    written: dict[str, list[tuple[str, bytes]]] = field(default_factory=dict)
    after: list[tuple[str, bool | None]] = field(default_factory=list)

    async def skill_exists(self, slug: str) -> bool:
        return slug in self.existing

    async def write_files(self, slug: str, files: list[tuple[str, bytes]]) -> None:
        self.written[slug] = list(files)
        self.existing.add(slug)

    async def after_install(self, slug: str, *, enable: bool | None = None) -> None:
        self.after.append((slug, enable))


@pytest.mark.asyncio
async def test_commit_writes_and_calls_after_install() -> None:
    target: SkillInstallTarget = FakeTarget()
    package = resolve_skill_package(
        slug="demo",
        files=[("SKILL.md", b"---\nname: demo\n---\n")],
        source="url",
        source_url="https://skills.sh/demo",
    )

    result = await commit_skill_install(target, package, overwrite=False, enable=True)

    assert result.slug == "demo"
    assert target.written["demo"] == [("SKILL.md", b"---\nname: demo\n---\n")]
    assert target.after == [("demo", True)]


@pytest.mark.asyncio
async def test_commit_rejects_existing_without_overwrite() -> None:
    target = FakeTarget(existing={"demo"})
    package = resolve_skill_package(
        slug="demo",
        files=[("SKILL.md", b"---\nname: demo\n---\n")],
        source="url",
    )

    with pytest.raises(SkillAlreadyExistsError) as exc:
        await commit_skill_install(target, package, overwrite=False)

    assert exc.value.slug == "demo"
    assert target.written == {}


@pytest.mark.asyncio
async def test_commit_overwrite_existing() -> None:
    target = FakeTarget(existing={"demo"})
    package = resolve_skill_package(
        slug="demo",
        files=[("SKILL.md", b"---\nname: demo\n---\nupdated")],
        source="url",
    )

    await commit_skill_install(target, package, overwrite=True, enable=None)

    assert target.written["demo"][0][1] == b"---\nname: demo\n---\nupdated"
    assert target.after == [("demo", None)]


def test_prepare_skillhub_package_adds_presentation_metadata() -> None:
    package = prepare_skillhub_package(
        "hub-skill",
        [("SKILL.md", b"---\nname: hub-skill\ndescription: x\n---\n\nbody\n")],
        display_name="展示名",
        icon_url="https://example.com/icon.png",
    )

    assert isinstance(package, ResolvedSkillPackage)
    assert package.slug == "hub-skill"
    assert package.source == "skillhub"
    manifest = next(content for path, content in package.files if path == "SKILL.md")
    text = manifest.decode("utf-8")
    assert "display_name: 展示名" in text
    assert "icon_url: https://example.com/icon.png" in text
    assert "source: skillhub" in text
