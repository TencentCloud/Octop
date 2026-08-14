"""Disk-backed content storage for global skill packages."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any

try:
    from psycopg import errors as pg_errors
except ImportError:  # pragma: no cover - optional PostgreSQL driver
    pg_errors = None  # type: ignore[assignment]

from octop.infra.db.repos.skill_packages import SkillPackageRepo, SkillPackageRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.skills.install import valid_skillhub_icon_url
from octop.infra.skills.skill_packages import (
    SkillPackageError,
    normalize_skill_files,
    validate_skill_slug,
)
from octop.infra.users.identity import User
from octop.infra.utils.frontmatter import parse_frontmatter
from octop.infra.utils.ulid import new_short_id


def is_skill_package_name_conflict(exc: BaseException) -> bool:
    """Return whether a database integrity error violates the package name key."""
    if isinstance(exc, sqlite3.IntegrityError):
        msg = str(exc).lower()
        return "unique" in msg and "skill_packages" in msg and "name" in msg
    if pg_errors is not None and isinstance(exc, pg_errors.UniqueViolation):
        msg = str(exc).lower()
        return "skill_packages" in msg and "name" in msg
    return False


def raise_skill_package_name_taken(name: str) -> None:
    raise OctopError.localized(
        ErrorCode.SKILL_PACKAGE_NAME_TAKEN,
        name=name,
        details={"name": name},
    )


def _apply_presentation_metadata(summary: dict[str, Any], metadata: dict[str, Any]) -> None:
    """Apply display_name / emoji / icon_url from SKILL.md extension namespaces."""
    extensions = metadata.get("metadata")
    if not isinstance(extensions, dict):
        return
    has_display_name = False
    for key in ("octop", "lightclaw", "orca", "harness", "openclaw"):
        extension = extensions.get(key)
        if not isinstance(extension, dict):
            continue
        display_name = str(extension.get("display_name") or "").strip()
        if display_name and not has_display_name:
            summary["name"] = display_name
            has_display_name = True
        emoji = str(extension.get("emoji") or "").strip()
        if emoji and "emoji" not in summary:
            summary["emoji"] = emoji
        icon_url = str(extension.get("icon_url") or "").strip()
        if icon_url and "icon_url" not in summary and valid_skillhub_icon_url(icon_url):
            summary["icon_url"] = icon_url


def _allocate_package_id(repo: SkillPackageRepo) -> str:
    for _ in range(16):
        package_id = new_short_id()
        if repo.get(package_id) is None:
            return package_id
    raise RuntimeError("failed to allocate unique skill package id")


class SkillPackageStore:
    """Persist skill package contents below a host-local root."""

    def __init__(self, *, repo: SkillPackageRepo, root: Path) -> None:
        self.repo = repo
        self.root = root

    def create(
        self,
        *,
        name: str,
        description: str,
        created_by: str,
        icon_name: str = "",
        icon_url: str = "",
    ) -> SkillPackageRow:
        row = self.repo.create(
            id=_allocate_package_id(self.repo),
            name=name,
            description=description,
            created_by=created_by,
            icon_name=icon_name,
            icon_url=icon_url,
        )
        self.package_skills_dir(row.id).mkdir(parents=True, exist_ok=True)
        return row

    def package_skills_dir(self, pack_id: str) -> Path:
        return self.root / pack_id / "skills"

    def list_skill_summaries(self, pack_id: str) -> list[dict[str, Any]]:
        skills_dir = self.package_skills_dir(pack_id)
        if not skills_dir.is_dir():
            return []

        summaries: list[dict[str, Any]] = []
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir() or skill_dir.is_symlink():
                continue
            manifest = skill_dir / "SKILL.md"
            try:
                text = manifest.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            metadata, _ = parse_frontmatter(text)
            if metadata.get("removed"):
                continue
            summary: dict[str, Any] = {
                "slug": skill_dir.name,
                "name": str(metadata.get("name") or skill_dir.name),
                "description": str(metadata.get("description") or ""),
                "path": f"skills/{skill_dir.name}/SKILL.md",
                "kind": "package",
                "package_id": pack_id,
            }
            _apply_presentation_metadata(summary, metadata)
            summaries.append(summary)
        return summaries

    def write_skill(
        self,
        pack_id: str,
        slug: str,
        files: list[tuple[str, bytes]],
    ) -> None:
        try:
            safe_slug = validate_skill_slug(slug)
            normalized_files = normalize_skill_files(files)
        except SkillPackageError as exc:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc)) from exc
        skill_dir = self.package_skills_dir(pack_id) / safe_slug

        shutil.rmtree(skill_dir, ignore_errors=True)
        skill_dir.mkdir(parents=True, exist_ok=True)
        for relative_path, content in normalized_files:
            path = skill_dir / relative_path
            if relative_path.endswith("/"):
                # Empty directory marker ("ai/"): recreate the folder, write nothing.
                path.mkdir(parents=True, exist_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self._update_skill_count(pack_id)

    def delete_skill(self, pack_id: str, slug: str) -> None:
        try:
            safe_slug = validate_skill_slug(slug)
        except SkillPackageError as exc:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc)) from exc
        skill_dir = self.package_skills_dir(pack_id) / safe_slug
        shutil.rmtree(skill_dir, ignore_errors=True)
        self._update_skill_count(pack_id)

    def delete_package(self, pack_id: str) -> None:
        self.repo.delete(pack_id)
        shutil.rmtree(self.root / pack_id, ignore_errors=True)

    def assert_can_mutate(self, row: SkillPackageRow, user: User) -> None:
        if user.is_admin or str(user.id) == row.created_by:
            return
        raise OctopError(ErrorCode.FORBIDDEN, "skill package can only be modified by its creator")

    def _update_skill_count(self, pack_id: str) -> None:
        self.repo.update_skill_count(pack_id, len(self.list_skill_summaries(pack_id)))
