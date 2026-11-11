"""Materialize a SkillHub skillset into a global skill package."""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from octop.infra.agents.experts.skillhub_market import (
    SkillHubSkillset,
    _scene_icon_name,
    fetch_skillset,
    skill_slugs_for_skillset,
)
from octop.infra.db.repos.skill_packages import SkillPackageRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.market import experts as portal_experts
from octop.infra.market import http as portal_http
from octop.infra.market.errors import PortalMarketError
from octop.infra.market.install import _install_zip
from octop.infra.market.normalize import pick_localized
from octop.infra.skills.install import valid_skillhub_icon_url
from octop.infra.skills.skill_package_store import (
    SkillPackageStore,
    is_skill_package_name_conflict,
    raise_skill_package_name_taken,
)
from octop.infra.skills.skill_packages import SkillPackageError, read_skill_directory
from octop.infra.skills.skillhub_market import (
    SkillHubSkillNotFound,
    download_skillhub_package_files,
)

logger = logging.getLogger(__name__)

SkillFiles = list[tuple[str, bytes]]
FetchSkillset = Callable[[str], SkillHubSkillset]
DownloadSkillFiles = Callable[[str], SkillFiles]


@dataclass(frozen=True)
class CreatePackageFromSkillHubResult:
    row: SkillPackageRow
    skipped_slugs: tuple[str, ...] = ()


def create_package_from_skillhub(
    store: SkillPackageStore,
    *,
    slug: str,
    created_by: str,
    name: str | None = None,
    description: str | None = None,
    icon_name: str | None = None,
    icon_url: str | None = None,
    shared: bool = False,
    fetch_skillset_fn: FetchSkillset | None = None,
    download_skill_files_fn: DownloadSkillFiles = download_skillhub_package_files,
) -> CreatePackageFromSkillHubResult:
    """Import portal workflows first, retaining the legacy SkillHub source fallback."""
    portal = portal_experts.get_market_expert(slug) if fetch_skillset_fn is None else None
    if portal is not None:
        item = SkillHubSkillset(
            slug=slug,
            display_name=pick_localized(portal.get("label"), "zh") or slug,
            summary=pick_localized(portal.get("description"), "zh"),
            scene=str(portal.get("scene") or ""),
            icon_url=str(portal.get("icon_url") or ""),
        )
    else:
        item = (fetch_skillset_fn or fetch_skillset)(slug)
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

    skipped_slugs: list[str]
    if portal is not None:
        skill_files, skipped_slugs = [(slug, _portal_package(item, portal))], []
    else:
        skill_files, skipped_slugs = _download_skillset_skills(
            slug, skill_slugs_for_skillset(item), download_skill_files_fn
        )
    try:
        row = store.create(
            name=package_name,
            description=package_description,
            created_by=created_by,
            icon_name=package_icon_name,
            icon_url=package_icon_url,
            shared=shared,
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
    return CreatePackageFromSkillHubResult(
        row=refreshed,
        skipped_slugs=tuple(skipped_slugs),
    )


def _portal_package(item: SkillHubSkillset, entry: dict[str, Any]) -> SkillFiles:
    """Keep an expert archive self-contained so child skills retain relative dependencies."""
    slug = item.slug
    url = entry.get("download_url")
    if not isinstance(url, str) or not portal_http.is_market_archive_url(url):
        raise PortalMarketError("expert package url is missing or outside the market origin")
    payload = portal_http.fetch_bytes(url, limit=portal_http.MAX_ARCHIVE_BYTES)
    size, digest = entry.get("size_bytes"), entry.get("sha256")
    if size is not None and (not isinstance(size, int) or size != len(payload)):
        raise PortalMarketError("expert package size does not match catalog")
    if digest is not None and (
        not isinstance(digest, str) or hashlib.sha256(payload).hexdigest() != digest.lower()
    ):
        raise PortalMarketError("expert package checksum does not match catalog")
    with tempfile.TemporaryDirectory() as temporary:
        cache = Path(temporary)
        _install_zip(payload, cache, slug)
        root = cache / slug
        children = sorted(root.glob("skills/*/SKILL.md"))
        if not children:
            raise PortalMarketError("expert package has no skills")
        if not (root / "SKILL.md").exists():
            instructions = [
                "Use this directory as the workflow root; keep scripts and references relative to it.",
                "Before running scripts that write profiles, state, or other files, copy this entire "
                "workflow directory into the current agent's workspace and work from that copy. "
                "Never write user data into the shared skill package directory.",
                "Read the following bundled instructions and skills as needed. "
                "Do not replace the host agent's system files with these templates.",
            ]
            instructions.extend(
                f"- [{name}]({name})"
                for name in ("SOUL.md", "AGENTS.md", "BOOTSTRAP.md")
                if (root / name).is_file()
            )
            instructions.extend(f"- {path.relative_to(root).as_posix()}" for path in children)
            manifest = (
                f"---\nname: {json.dumps(slug)}\n"
                f"description: {json.dumps(item.summary or item.display_name, ensure_ascii=False)}\n"
                f"---\n\n# {item.display_name}\n\n" + "\n".join(instructions) + "\n"
            )
            (root / "SKILL.md").write_text(manifest, encoding="utf-8")
        try:
            return read_skill_directory(root)
        except SkillPackageError as exc:
            raise PortalMarketError("expert package contains invalid skill files") from exc


def _download_skillset_skills(
    skillset_slug: str,
    skill_slugs: list[str],
    download_skill_files_fn: DownloadSkillFiles,
) -> tuple[list[tuple[str, SkillFiles]], list[str]]:
    """Download each skill. A missing package (HTTP 404) is skipped.

    SkillHub skillsets can list a slug whose metadata still exists while the
    zip object is gone. Failing the whole import on that one 404 blocks every
    other skill in the set.
    """
    downloaded: list[tuple[str, SkillFiles]] = []
    skipped: list[str] = []
    missing: SkillHubSkillNotFound | None = None
    for skill_slug in skill_slugs:
        try:
            downloaded.append((skill_slug, download_skill_files_fn(skill_slug)))
        except SkillHubSkillNotFound as exc:
            logger.warning(
                "skipping unpublished SkillHub skill %s from skillset %s: %s",
                skill_slug,
                skillset_slug,
                exc,
            )
            skipped.append(skill_slug)
            missing = exc
    if not downloaded:
        if missing is not None:
            raise missing
        raise SkillHubSkillNotFound(
            f"SkillHub skillset {skillset_slug!r} has no downloadable skills"
        )
    return downloaded, skipped
