"""Shared skill install pipeline for agent workspace and global packages."""

from __future__ import annotations

from typing import Protocol
from urllib.parse import urlparse

import yaml

from octop.infra.skills import skills_hub
from octop.infra.skills.skill_packages import (
    ResolvedSkillPackage,
    SkillPackageError,
    resolve_skill_package,
    resolve_workspace_uploads,
    validate_skill_slug,
)
from octop.infra.utils.frontmatter import parse_frontmatter


class SkillAlreadyExistsError(Exception):
    """Skill slug already exists in the install target and overwrite is false."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"skill already exists: {slug}")


class SkillInstallTarget(Protocol):
    """Destination for a resolved skill package (agent workspace or package store)."""

    async def skill_exists(self, slug: str) -> bool: ...

    async def write_files(self, slug: str, files: list[tuple[str, bytes]]) -> None: ...

    async def after_install(self, slug: str, *, enable: bool | None = None) -> None: ...


def _valid_skillhub_icon_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def with_skillhub_presentation_metadata(
    content: str,
    *,
    display_name: str,
    icon_url: str,
) -> str:
    """Persist SkillHub presentation fields without changing the stable skill id."""
    if not display_name and not icon_url:
        return content

    meta, body = parse_frontmatter(content)
    metadata = meta.get("metadata")
    metadata = {} if not isinstance(metadata, dict) else dict(metadata)
    octop_meta = metadata.get("octop")
    octop_meta = {} if not isinstance(octop_meta, dict) else dict(octop_meta)

    octop_meta["source"] = "skillhub"
    if display_name:
        octop_meta["display_name"] = display_name
    if icon_url:
        octop_meta["icon_url"] = icon_url
    metadata["octop"] = octop_meta
    meta["metadata"] = metadata

    dumped = yaml.safe_dump(
        meta,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).rstrip()
    rendered = f"---\n{dumped}\n---\n"
    if body:
        rendered += f"\n{body}"
    if content.endswith("\n") and not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


def prepare_skillhub_package(
    skill_name: str,
    files: list[tuple[str, bytes]],
    *,
    display_name: str = "",
    icon_url: str = "",
) -> ResolvedSkillPackage:
    """Normalize SkillHub download files into a canonical package."""
    safe_name = validate_skill_slug(skill_name)
    transformed: list[tuple[str, bytes]] = []
    for rel, original_content in files:
        normalized = rel.replace("\\", "/")
        content = original_content
        if normalized == "SKILL.md":
            try:
                manifest = content.decode("utf-8")
            except UnicodeDecodeError:
                pass
            else:
                content = with_skillhub_presentation_metadata(
                    manifest,
                    display_name=display_name,
                    icon_url=icon_url,
                ).encode("utf-8")
        transformed.append((normalized, content))
    return resolve_skill_package(
        slug=safe_name,
        files=transformed,
        source="skillhub",
    )


def resolve_url_import(
    *,
    bundle_url: str,
    version: str | None = None,
) -> ResolvedSkillPackage:
    """Download/resolve a skill URL into a canonical package."""
    resolved = skills_hub.resolve_bundle_from_url(
        bundle_url=bundle_url,
        version=version or "",
    )
    return resolve_workspace_uploads(
        slug=resolved.name,
        uploads=resolved.uploads,
        source="url",
        source_url=resolved.source_url,
    )


async def commit_skill_install(
    target: SkillInstallTarget,
    package: ResolvedSkillPackage,
    *,
    overwrite: bool = False,
    enable: bool | None = None,
) -> ResolvedSkillPackage:
    """Write a resolved package into the target and run post-install hooks."""
    if await target.skill_exists(package.slug) and not overwrite:
        raise SkillAlreadyExistsError(package.slug)
    await target.write_files(package.slug, list(package.files))
    await target.after_install(package.slug, enable=enable)
    return package


async def install_skill_from_url(
    target: SkillInstallTarget,
    *,
    bundle_url: str,
    version: str | None = None,
    overwrite: bool = False,
    enable: bool | None = None,
) -> ResolvedSkillPackage:
    """Resolve a skill URL and commit it into the target."""
    package = resolve_url_import(bundle_url=bundle_url, version=version)
    return await commit_skill_install(
        target,
        package,
        overwrite=overwrite,
        enable=enable,
    )


async def install_skill_from_skillhub(
    target: SkillInstallTarget,
    *,
    skill_name: str,
    files: list[tuple[str, bytes]],
    display_name: str = "",
    icon_url: str = "",
    overwrite: bool = False,
    enable: bool | None = None,
) -> ResolvedSkillPackage:
    """Prepare SkillHub files and commit them into the target."""
    if not files:
        raise SkillPackageError(f"skillhub installed nothing for '{skill_name}'")
    package = prepare_skillhub_package(
        skill_name,
        files,
        display_name=display_name,
        icon_url=icon_url,
    )
    return await commit_skill_install(
        target,
        package,
        overwrite=overwrite,
        enable=enable,
    )


def valid_skillhub_icon_url(value: str) -> bool:
    """Public alias used by HTTP routers for icon URL validation."""
    return _valid_skillhub_icon_url(value)


__all__ = [
    "SkillAlreadyExistsError",
    "SkillInstallTarget",
    "commit_skill_install",
    "install_skill_from_skillhub",
    "install_skill_from_url",
    "prepare_skillhub_package",
    "resolve_url_import",
    "valid_skillhub_icon_url",
    "with_skillhub_presentation_metadata",
]
