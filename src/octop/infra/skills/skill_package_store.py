"""Disk-backed content storage for global skill packages."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from psycopg import errors as pg_errors
except ImportError:  # pragma: no cover - optional PostgreSQL driver
    pg_errors = None  # type: ignore[assignment]

from octop.infra.db.repos.skill_packages import SkillPackageRepo, SkillPackageRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.skills.presentation import apply_skill_presentation
from octop.infra.skills.skill_packages import (
    SkillPackageError,
    normalize_skill_files,
    validate_skill_slug,
)
from octop.infra.users.identity import User
from octop.infra.utils.frontmatter import parse_frontmatter
from octop.infra.utils.locale import Locale
from octop.infra.utils.ulid import new_short_id

logger = logging.getLogger(__name__)


COPY_POLICIES = ("snapshot", "lock", "deny")


def normalize_copy_policy(value: object) -> str:
    """Clamp a stored/configured copy policy to the supported set (#770)."""
    text = str(value or "").strip().lower()
    return text if text in COPY_POLICIES else "snapshot"


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
        shared: bool = False,
        copy_policy: str = "snapshot",
        allow_download: bool = True,
    ) -> SkillPackageRow:
        row = self.repo.create(
            id=_allocate_package_id(self.repo),
            name=name,
            description=description,
            created_by=created_by,
            icon_name=icon_name,
            icon_url=icon_url,
            shared=shared,
            copy_policy=normalize_copy_policy(copy_policy),
            allow_download=allow_download,
        )
        self.package_skills_dir(row.id).mkdir(parents=True, exist_ok=True)
        return row

    def package_skills_dir(self, pack_id: str) -> Path:
        return self.root / pack_id / "skills"

    def list_skill_summaries(
        self,
        pack_id: str,
        *,
        locale: Locale | None = None,
    ) -> list[dict[str, Any]]:
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
            except UnicodeDecodeError:
                from octop.infra.utils.utf8_text import repair_skill_manifest_file

                repaired = repair_skill_manifest_file(manifest)
                if repaired is None:
                    logger.warning(
                        "skipping package skill %s/%s: SKILL.md is not valid UTF-8",
                        pack_id,
                        skill_dir.name,
                    )
                    summaries.append(
                        {
                            "slug": skill_dir.name,
                            "name": skill_dir.name,
                            "description": "",
                            "path": f"skills/{skill_dir.name}/SKILL.md",
                            "kind": "package",
                            "package_id": pack_id,
                            "enabled": False,
                            "corrupt": True,
                            "error": "invalid_utf8",
                        }
                    )
                    continue
                text = repaired
            except OSError:
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
            summaries.append(apply_skill_presentation(summary, metadata, locale=locale))
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

    def write_skill_manifest(self, pack_id: str, slug: str, content: str) -> None:
        """Overwrite SKILL.md in place, preserving sibling files and directories."""
        try:
            safe_slug = validate_skill_slug(slug)
        except SkillPackageError as exc:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc)) from exc
        try:
            payload = content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "SKILL.md must be UTF-8 text") from exc
        skill_dir = self.package_skills_dir(pack_id) / safe_slug
        manifest = skill_dir / "SKILL.md"
        if not manifest.is_file():
            raise OctopError(ErrorCode.NOT_FOUND, f"skill {slug!r} not found")
        manifest.write_bytes(payload)

    def _safe_slug(self, slug: str) -> str:
        try:
            return validate_skill_slug(slug)
        except SkillPackageError as exc:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc)) from exc

    def _skill_dir(self, pack_id: str, slug: str) -> Path:
        safe_slug = self._safe_slug(slug)
        skill_dir = self.package_skills_dir(pack_id) / safe_slug
        if not skill_dir.is_dir():
            raise OctopError(ErrorCode.NOT_FOUND, f"skill {slug!r} not found")
        return skill_dir

    def resolve_skill_entry(self, pack_id: str, slug: str, relative_path: str = "") -> Path:
        """Resolve ``relative_path`` under a package skill; reject traversal."""
        skill_dir = self._skill_dir(pack_id, slug)
        text = (relative_path or "").strip().replace("\\", "/").lstrip("/")
        safe_slug = skill_dir.name
        prefix = f"skills/{safe_slug}/"
        if text.startswith(prefix):
            text = text[len(prefix) :]
        elif text == f"skills/{safe_slug}":
            text = ""
        if not text or text in {".", "./"}:
            return skill_dir
        try:
            normalized = PurePosixPath(text)
        except ValueError as exc:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid path: {relative_path!r}") from exc
        if (
            normalized.is_absolute()
            or ".." in normalized.parts
            or (normalized.parts and normalized.parts[0].endswith(":"))
        ):
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"unsafe path: {relative_path!r}")
        target = (skill_dir / Path(*normalized.parts)).resolve()
        try:
            target.relative_to(skill_dir.resolve())
        except ValueError as exc:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"unsafe path: {relative_path!r}") from exc
        return target

    def list_skill_tree(
        self,
        pack_id: str,
        slug: str,
        relative_path: str = "",
    ) -> list[dict[str, Any]]:
        """Single-level directory listing under a package skill path."""
        skill_dir = self._skill_dir(pack_id, slug)
        target = self.resolve_skill_entry(pack_id, slug, relative_path)
        if not target.is_dir() or target.is_symlink():
            raise OctopError(ErrorCode.NOT_FOUND, f"cannot list {relative_path or '.'!r}")
        logical_root = f"skills/{skill_dir.name}"
        rows: list[dict[str, Any]] = []
        try:
            entries = sorted(
                target.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except OSError as exc:
            raise OctopError(ErrorCode.NOT_FOUND, f"cannot list {relative_path or '.'!r}") from exc
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                is_dir = entry.is_dir()
                rel = entry.relative_to(skill_dir).as_posix()
                row: dict[str, Any] = {
                    "path": f"{logical_root}/{rel}",
                    "is_dir": is_dir,
                }
                if not is_dir:
                    row["size"] = entry.stat().st_size
                rows.append(row)
            except OSError:
                continue
        return rows

    def read_skill_file_text(self, pack_id: str, slug: str, relative_path: str) -> str:
        target = self.resolve_skill_entry(pack_id, slug, relative_path)
        if not target.is_file() or target.is_symlink():
            raise OctopError(ErrorCode.NOT_FOUND, f"cannot read {relative_path!r}")
        try:
            return target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                f"file is not UTF-8 text: {relative_path!r}",
            ) from exc
        except OSError as exc:
            raise OctopError(ErrorCode.NOT_FOUND, f"cannot read {relative_path!r}") from exc

    def read_skill_file_bytes(self, pack_id: str, slug: str, relative_path: str) -> bytes:
        target = self.resolve_skill_entry(pack_id, slug, relative_path)
        if not target.is_file() or target.is_symlink():
            raise OctopError(ErrorCode.NOT_FOUND, f"cannot read {relative_path!r}")
        try:
            return target.read_bytes()
        except OSError as exc:
            raise OctopError(ErrorCode.NOT_FOUND, f"cannot read {relative_path!r}") from exc

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
        if self.can_mutate(row, user):
            return
        raise OctopError(ErrorCode.FORBIDDEN, "skill package can only be modified by its creator")

    def can_view(self, row: SkillPackageRow, user: User) -> bool:
        """Whether *user* may see / mount / read this package."""
        if self.can_mutate(row, user):
            return True
        return bool(getattr(row, "shared", False))

    def assert_can_view(self, row: SkillPackageRow, user: User) -> None:
        if self.can_view(row, user):
            return
        raise OctopError(ErrorCode.SKILL_PACKAGE_NOT_FOUND, "skill package not found")

    def can_copy(self, row: SkillPackageRow, user: User) -> bool:
        """Whether *user* may copy this package's skills into a workspace (#770)."""
        if not self.can_view(row, user):
            return False
        return self.can_mutate(row, user) or normalize_copy_policy(row.copy_policy) != "deny"

    def assert_can_copy(self, row: SkillPackageRow, user: User) -> None:
        self.assert_can_view(row, user)
        if self.can_mutate(row, user) or normalize_copy_policy(row.copy_policy) != "deny":
            return
        raise OctopError(
            ErrorCode.SKILL_PACKAGE_COPY_DENIED,
            f"skill package {row.id!r} does not allow copying",
        )

    def can_download(self, row: SkillPackageRow, user: User) -> bool:
        """Whether *user* may download this package as a ZIP."""
        if not self.can_view(row, user):
            return False
        if self.can_mutate(row, user):
            return True
        return bool(getattr(row, "allow_download", True))

    def assert_can_download(self, row: SkillPackageRow, user: User) -> None:
        self.assert_can_view(row, user)
        if self.can_mutate(row, user) or bool(getattr(row, "allow_download", True)):
            return
        raise OctopError(
            ErrorCode.SKILL_PACKAGE_DOWNLOAD_DENIED,
            f"skill package {row.id!r} does not allow download",
        )

    def can_mutate(self, row: SkillPackageRow, user: User) -> bool:
        return user.is_admin or str(user.id) == row.created_by

    def _update_skill_count(self, pack_id: str) -> None:
        self.repo.update_skill_count(pack_id, len(self.list_skill_summaries(pack_id)))
