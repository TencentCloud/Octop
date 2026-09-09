"""Copy skills between global packages and agent workspaces."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from octop.infra.skills.skill_package_store import SkillPackageStore
from octop.infra.skills.skill_packages import (
    MAX_SKILL_BYTES,
    MAX_SKILL_FILES,
    SkillPackageError,
    SkillPackageTooLarge,
    normalize_skill_files,
    read_skill_directory,
    validate_skill_slug,
)
from octop.infra.utils.frontmatter import parse_frontmatter


class SkillTransferConflict(SkillPackageError):
    """A destination already contains a live skill with the same slug."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"skill {slug!r} already exists")
        self.slug = slug


class SkillTransferNotFound(SkillPackageError):
    """The selected source skill does not exist."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"skill {slug!r} not found")
        self.slug = slug


def _entry_fields(entry: Any) -> tuple[str, bool]:
    if isinstance(entry, dict):
        path = entry.get("path")
        is_dir = entry.get("is_dir", False)
    else:
        path = getattr(entry, "path", None)
        is_dir = getattr(entry, "is_dir", False)
    return str(path or ""), bool(is_dir)


def _entry_name(path: str) -> str:
    name = path.strip().replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        raise SkillPackageError(f"invalid workspace entry path: {path}")
    return name


def _is_live_manifest(content: str | None) -> bool:
    if content is None:
        return False
    metadata, _body = parse_frontmatter(content)
    return not bool(metadata.get("removed"))


async def read_workspace_skill_files(
    workspace: Any,
    slug: str,
) -> list[tuple[str, bytes]]:
    """Read one skill recursively through the workspace abstraction."""
    safe_slug = validate_skill_slug(slug)
    root = f"skills/{safe_slug}"
    manifest = await workspace.aread_text(f"{root}/SKILL.md")
    if not _is_live_manifest(manifest):
        raise SkillTransferNotFound(safe_slug)

    files: list[tuple[str, bytes]] = []
    total_bytes = 0
    pending: list[tuple[str, str]] = [(root, "")]
    visited: set[str] = set()
    while pending:
        current, relative_dir = pending.pop()
        if current in visited:
            raise SkillPackageError(f"workspace contains a directory cycle: {current}")
        visited.add(current)
        if len(visited) > MAX_SKILL_FILES:
            raise SkillPackageTooLarge("skill package has too many directories")

        result = await workspace.als(current)
        if result is None:
            raise SkillPackageError(f"workspace cannot list skill directory: {current}")
        entries = getattr(result, "entries", None) or []
        for entry in entries:
            raw_path, is_dir = _entry_fields(entry)
            name = _entry_name(raw_path)
            child = f"{current}/{name}"
            relative_path = f"{relative_dir}/{name}" if relative_dir else name
            if is_dir:
                pending.append((child, relative_path))
                continue
            content = await workspace.adownload_bytes(child)
            if content is None:
                raise SkillPackageError(f"workspace cannot read skill file: {child}")
            files.append((relative_path, content))
            total_bytes += len(content)
            if len(files) > MAX_SKILL_FILES:
                raise SkillPackageTooLarge("skill package has too many files")
            if total_bytes > MAX_SKILL_BYTES:
                raise SkillPackageTooLarge("skill package size exceeds 64 MB")

    return list(normalize_skill_files(files))


async def _write_workspace_skill(
    workspace: Any,
    slug: str,
    files: Sequence[tuple[str, bytes]],
) -> None:
    root = f"skills/{slug}"
    if await workspace.aexists(root):
        await workspace.adelete(root)
    directories = [path for path, _content in files if path.endswith("/")]
    for path in directories:
        await workspace.amkdir(f"{root}/{path}".rstrip("/"))
    payload = [(f"{root}/{path}", content) for path, content in files if not path.endswith("/")]
    if payload:
        await workspace.aupload_many(payload)


async def copy_package_skills_to_workspace(
    *,
    store: SkillPackageStore,
    package_id: str,
    slugs: Sequence[str],
    workspace: Any,
    overwrite: bool = False,
) -> list[str]:
    """Copy selected package skills into a workspace as independent snapshots."""
    selected = list(dict.fromkeys(validate_skill_slug(slug) for slug in slugs))
    if not selected:
        raise SkillPackageError("at least one skill is required")

    sources: dict[str, list[tuple[str, bytes]]] = {}
    for slug in selected:
        skill_dir = store.package_skills_dir(package_id) / slug
        if not (skill_dir / "SKILL.md").is_file():
            raise SkillTransferNotFound(slug)
        sources[slug] = read_skill_directory(skill_dir)

    if not overwrite:
        for slug in selected:
            existing = await workspace.aread_text(f"skills/{slug}/SKILL.md")
            if _is_live_manifest(existing):
                raise SkillTransferConflict(slug)

    for slug in selected:
        await _write_workspace_skill(workspace, slug, sources[slug])
    return selected


async def copy_workspace_skill_to_package(
    *,
    workspace: Any,
    store: SkillPackageStore,
    package_id: str,
    slug: str,
    overwrite: bool = False,
) -> str:
    """Copy a workspace skill into a writable global package."""
    safe_slug = validate_skill_slug(slug)
    files = await read_workspace_skill_files(workspace, safe_slug)
    destination = store.package_skills_dir(package_id) / safe_slug / "SKILL.md"
    if destination.is_file() and not overwrite:
        raise SkillTransferConflict(safe_slug)
    store.write_skill(package_id, safe_slug, files)
    return safe_slug
