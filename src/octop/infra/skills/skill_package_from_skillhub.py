"""Materialize a SkillHub skillset into a global skill package."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from octop.infra.agents.experts.skillhub_market import (
    SkillHubSkillset,
    _scene_icon_name,
    fetch_skillset,
    skill_slugs_for_skillset,
)
from octop.infra.db.repos.skill_packages import SkillPackageRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.skills.install import valid_skillhub_icon_url
from octop.infra.skills.skill_package_store import (
    SkillPackageStore,
    is_skill_package_name_conflict,
    raise_skill_package_name_taken,
)
from octop.infra.skills.skillhub_market import download_skillhub_package_files

SkillFiles = list[tuple[str, bytes]]
FetchSkillset = Callable[[str], SkillHubSkillset]
DownloadSkillFiles = Callable[[str], SkillFiles]


@dataclass(frozen=True)
class CreatePackageFromSkillHubResult:
    row: SkillPackageRow


def create_package_from_skillhub(
    store: SkillPackageStore,
    *,
    slug: str,
    created_by: str,
    name: str | None = None,
    description: str | None = None,
    icon_name: str | None = None,
    icon_url: str | None = None,
    fetch_skillset_fn: FetchSkillset = fetch_skillset,
    download_skill_files_fn: DownloadSkillFiles = download_skillhub_package_files,
) -> CreatePackageFromSkillHubResult:
    """Create a global package from a SkillHub skillset without using its cache."""
    item = fetch_skillset_fn(slug)
    package_name = (name if name is not None else item.display_name).strip()
    package_description = (description if description is not None else item.summary).strip()
    package_icon_name = (
        icon_name if icon_name is not None else _scene_icon_name(item.scene)
    ).strip()
    package_icon_url = (icon_url if icon_url is not None else item.icon_url).strip()

    if package_icon_url and not valid_skillhub_icon_url(package_icon_url):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid SkillHub icon URL")
    if store.repo.get_by_name(package_name) is not None:
        raise_skill_package_name_taken(package_name)

    skill_slugs = skill_slugs_for_skillset(item)
    skill_files = [(skill_slug, download_skill_files_fn(skill_slug)) for skill_slug in skill_slugs]
    try:
        row = store.create(
            name=package_name,
            description=package_description,
            created_by=created_by,
            icon_name=package_icon_name,
            icon_url=package_icon_url,
        )
    except Exception as exc:
        if is_skill_package_name_conflict(exc):
            raise_skill_package_name_taken(package_name)
        raise
    try:
        for skill_slug, files in skill_files:
            store.write_skill(row.id, skill_slug, files)
    except Exception:
        store.delete_package(row.id)
        raise
    refreshed = store.repo.get(row.id)
    if refreshed is None:
        raise RuntimeError(f"skill package {row.id} missing after create")
    return CreatePackageFromSkillHubResult(row=refreshed)
