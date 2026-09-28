"""Symlink-tolerant workspace skill discovery for Octop."""

from __future__ import annotations

import logging
import stat
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from octop.infra.agents.workspace.dir import (
    skills_discovery_roots_with_packages,
)
from octop.infra.skills.presentation import apply_skill_presentation
from octop.infra.utils.frontmatter import parse_frontmatter
from octop.infra.utils.utf8_text import repair_skill_manifest_file

logger = logging.getLogger(__name__)


def _summary_dict(
    slug: str,
    meta: dict[str, Any],
    *,
    enabled: bool,
    kind: str = "workspace",
) -> dict[str, Any]:
    return apply_skill_presentation(
        {
            "slug": slug,
            "name": str(meta.get("name") or slug),
            "description": str(meta.get("description") or ""),
            "enabled": enabled,
            "kind": kind,
        },
        meta,
    )


def _corrupt_summary(slug: str, *, reason: str, kind: str = "workspace") -> dict[str, Any]:
    return {
        "slug": slug,
        "name": slug,
        "description": "",
        "enabled": False,
        "kind": kind,
        "corrupt": True,
        "error": reason,
    }


def _read_manifest(skill_dir: Path) -> tuple[str | None, str | None]:
    """Return ``(text, error_code)``. Exactly one side is set on success/failure."""
    manifest = skill_dir / "SKILL.md"
    try:
        entry = manifest.lstat()
    except OSError:
        return None, "missing"
    if not stat.S_ISREG(entry.st_mode):
        return None, "missing"
    try:
        return manifest.read_text(encoding="utf-8"), None
    except UnicodeDecodeError:
        repaired = repair_skill_manifest_file(manifest)
        if repaired is not None:
            return repaired, None
        logger.warning(
            "skipping skill %s: SKILL.md is not valid UTF-8 (%s)",
            skill_dir.name,
            manifest,
        )
        return None, "invalid_utf8"
    except OSError:
        logger.warning("failed reading skill manifest at %s", manifest, exc_info=True)
        return None, "unreadable"


def _ordered_roots(
    workspace_dir: Path,
    package_dirs: Iterable[str | Path] = (),
) -> list[tuple[Path, str]]:
    """Existing, de-duplicated ``(root, kind)`` scan roots in contract order.

    Package roots come first (see
    :func:`skills_discovery_roots_with_packages`), and ``seen`` mirrors the
    original de-duplication so a symlinked package root cannot be scanned twice.
    With ``package_dirs`` empty this is exactly ``_skills_roots`` plus a kind.
    """
    roots: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    for root, kind in skills_discovery_roots_with_packages(workspace_dir, package_dirs):
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved in seen or not root.is_dir():
            continue
        seen.add(resolved)
        roots.append((root, kind))
    return roots


def _skills_roots(workspace_dir: Path) -> list[Path]:
    return [root for root, _kind in _ordered_roots(workspace_dir)]


def _resolve_skill_dir(
    workspace_dir: Path,
    slug: str,
    *,
    package_dirs: Iterable[str | Path] = (),
) -> Path | None:
    for skills_root, _kind in _ordered_roots(workspace_dir, package_dirs):
        skill_dir = skills_root / slug
        try:
            entry = skill_dir.lstat()
        except OSError:
            continue
        if stat.S_ISLNK(entry.st_mode) or stat.S_ISDIR(entry.st_mode):
            try:
                resolved = skill_dir.resolve()
            except OSError:
                logger.debug("failed resolving skill dir %s", skill_dir, exc_info=True)
                continue
            if resolved.is_dir():
                return resolved
    return None


def repair_workspace_skill_manifests(workspace_dir: Path) -> list[str]:
    """Repair known UTF-8 corruption in workspace skill manifests.

    Returns slugs that were rewritten. Unrepairable manifests are left in place
    for :func:`list_workspace_skill_summaries` to surface as ``corrupt``.
    """
    repaired: list[str] = []
    for skills_root in _skills_roots(workspace_dir):
        try:
            entries = list(skills_root.iterdir())
        except OSError:
            continue
        for entry in entries:
            slug = entry.name
            if not slug or slug.startswith("."):
                continue
            skill_dir = _resolve_skill_dir(workspace_dir, slug)
            if skill_dir is None:
                continue
            if repair_skill_manifest_file(skill_dir / "SKILL.md") is not None:
                repaired.append(slug)
    return repaired


def list_workspace_skill_summaries(
    workspace_dir: Path,
    *,
    skills_disabled: set[str] | frozenset[str],
    include_corrupt: bool = True,
    package_dirs: Iterable[str | Path] = (),
) -> list[dict[str, Any]]:
    """Scan ``skills/`` including ``.octop/skills`` and symlinked directories.

    ``package_dirs`` are mounted skill-package roots. They are scanned **first**,
    so when one slug is provided by both a package and the workspace the package
    wins and the workspace copy is skipped (PLAN.md §2.2 S3) — the ``seen`` set
    below *is* that rule, so no separate conflict pass exists. Rows found under a
    package root are labelled ``kind="package"``, matching the runtime path.

    Omitting ``package_dirs`` reproduces the previous behaviour exactly.
    """
    seen: set[str] = set()
    summaries: list[dict[str, Any]] = []
    for skills_root, kind in _ordered_roots(workspace_dir, package_dirs):
        try:
            entries = list(skills_root.iterdir())
        except OSError:
            continue
        for entry in sorted(entries, key=lambda path: path.name):
            slug = entry.name
            if not slug or slug.startswith(".") or slug in seen:
                continue
            skill_dir = _resolve_skill_dir(workspace_dir, slug, package_dirs=package_dirs)
            if skill_dir is None:
                continue
            manifest, error = _read_manifest(skill_dir)
            if manifest is None:
                if include_corrupt and error == "invalid_utf8":
                    seen.add(slug)
                    summaries.append(_corrupt_summary(slug, reason="invalid_utf8", kind=kind))
                continue
            meta, _body = parse_frontmatter(manifest)
            if meta.get("removed"):
                continue
            display_name = str(meta.get("name") or slug)
            seen.add(slug)
            summaries.append(
                _summary_dict(
                    slug,
                    meta,
                    enabled=slug not in skills_disabled and display_name not in skills_disabled,
                    kind=kind,
                )
            )
    return summaries


__all__ = [
    "list_workspace_skill_summaries",
    "repair_workspace_skill_manifests",
]
