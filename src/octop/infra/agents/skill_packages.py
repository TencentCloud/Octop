"""Source-neutral skill package validation and workspace path normalization."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MAX_SKILL_FILES = 2_000
MAX_SKILL_BYTES = 64 * 1024 * 1024


class SkillPackageError(ValueError):
    """A resolved skill package is invalid."""


class SkillPackageTooLarge(SkillPackageError):
    """A resolved skill package exceeded a safety limit."""


@dataclass(frozen=True)
class ResolvedSkillPackage:
    """Canonical package produced by any skill source adapter."""

    slug: str
    files: tuple[tuple[str, bytes], ...]
    source: str
    source_url: str = ""

    def workspace_uploads(self) -> list[tuple[str, bytes]]:
        return [
            (f"skills/{self.slug}/{relative_path}", content)
            for relative_path, content in self.files
        ]


def validate_skill_slug(slug: str) -> str:
    normalized = slug.strip()
    if (
        not normalized
        or normalized.startswith(".")
        or "/" in normalized
        or "\\" in normalized
        or "\x00" in normalized
    ):
        raise SkillPackageError("invalid skill name")
    return normalized


def _normalize_relative_path(value: str) -> str:
    if not value or "\\" in value or "\x00" in value:
        raise SkillPackageError(f"invalid skill package path: {value}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or (path.parts and path.parts[0].endswith(":")):
        raise SkillPackageError(f"unsafe skill package path: {value}")
    normalized = path.as_posix()
    if normalized in {"", "."}:
        raise SkillPackageError(f"invalid skill package path: {value}")
    return normalized


def normalize_skill_files(
    files: list[tuple[str, bytes]],
    *,
    require_manifest: bool = True,
) -> tuple[tuple[str, bytes], ...]:
    """Validate and canonicalize source-relative skill files."""
    if len(files) > MAX_SKILL_FILES:
        raise SkillPackageTooLarge("skill package has too many files")

    normalized: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    total = 0
    for relative_path, content in files:
        path = _normalize_relative_path(relative_path)
        if path in seen:
            raise SkillPackageError(f"duplicate skill package path: {path}")
        if not isinstance(content, bytes):
            raise SkillPackageError(f"skill package content must be bytes: {path}")
        seen.add(path)
        total += len(content)
        if total > MAX_SKILL_BYTES:
            raise SkillPackageTooLarge("skill package size exceeds 64 MB")
        normalized.append((path, content))

    if require_manifest and "SKILL.md" not in seen:
        raise SkillPackageError("skill package does not contain a root SKILL.md")
    if require_manifest:
        manifest = next(content for path, content in normalized if path == "SKILL.md")
        try:
            manifest.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SkillPackageError("skill package SKILL.md must be UTF-8 text") from exc
    return tuple(normalized)


def resolve_skill_package(
    *,
    slug: str,
    files: list[tuple[str, bytes]],
    source: str,
    source_url: str = "",
) -> ResolvedSkillPackage:
    return ResolvedSkillPackage(
        slug=validate_skill_slug(slug),
        files=normalize_skill_files(files),
        source=source.strip() or "unknown",
        source_url=source_url.strip(),
    )


def resolve_workspace_uploads(
    *,
    slug: str,
    uploads: list[tuple[str, bytes]],
    source: str,
    source_url: str = "",
) -> ResolvedSkillPackage:
    """Convert legacy workspace upload pairs into a canonical package."""
    safe_slug = validate_skill_slug(slug)
    prefix = f"skills/{safe_slug}/"
    files: list[tuple[str, bytes]] = []
    for path, content in uploads:
        if not path.startswith(prefix):
            raise SkillPackageError(f"skill upload is outside {prefix}: {path}")
        files.append((path[len(prefix) :], content))
    return resolve_skill_package(
        slug=safe_slug,
        files=files,
        source=source,
        source_url=source_url,
    )


def read_skill_directory(skill_dir: Path) -> list[tuple[str, bytes]]:
    """Read a CLI-produced package without following links."""
    files: list[tuple[str, bytes]] = []
    total = 0
    for dirpath, dirnames, filenames in os.walk(skill_dir, followlinks=False):
        current = Path(dirpath)
        for dirname in dirnames:
            if (current / dirname).is_symlink():
                raise SkillPackageError(f"unsupported symlink in skill package: {dirname}")
        for filename in filenames:
            path = current / filename
            entry_stat = path.lstat()
            if stat.S_ISLNK(entry_stat.st_mode) or not stat.S_ISREG(entry_stat.st_mode):
                raise SkillPackageError(f"unsupported file type in skill package: {filename}")
            total += entry_stat.st_size
            if total > MAX_SKILL_BYTES:
                raise SkillPackageTooLarge("skill package size exceeds 64 MB")
            files.append((path.relative_to(skill_dir).as_posix(), path.read_bytes()))
            if len(files) > MAX_SKILL_FILES:
                raise SkillPackageTooLarge("skill package has too many files")
    return list(normalize_skill_files(files))


__all__ = [
    "MAX_SKILL_BYTES",
    "MAX_SKILL_FILES",
    "ResolvedSkillPackage",
    "SkillPackageError",
    "SkillPackageTooLarge",
    "normalize_skill_files",
    "read_skill_directory",
    "resolve_skill_package",
    "resolve_workspace_uploads",
    "validate_skill_slug",
]
