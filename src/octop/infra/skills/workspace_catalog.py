"""Symlink-tolerant workspace skill discovery for Octop."""

from __future__ import annotations

import logging
import stat
from pathlib import Path
from typing import Any

from octop.infra.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)

_SKILLS_ROOT = "skills"


def _summary_dict(
    slug: str,
    meta: dict[str, Any],
    *,
    enabled: bool,
) -> dict[str, Any]:
    return {
        "slug": slug,
        "name": str(meta.get("name") or slug),
        "description": str(meta.get("description") or ""),
        "enabled": enabled,
        "kind": "workspace",
    }


def _read_manifest(skill_dir: Path) -> str | None:
    manifest = skill_dir / "SKILL.md"
    try:
        entry = manifest.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(entry.st_mode):
        return None
    try:
        return manifest.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.debug("failed reading skill manifest at %s", manifest, exc_info=True)
        return None


def _resolve_skill_dir(workspace_dir: Path, slug: str) -> Path | None:
    skill_dir = workspace_dir / _SKILLS_ROOT / slug
    try:
        entry = skill_dir.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(entry.st_mode) or stat.S_ISDIR(entry.st_mode):
        try:
            resolved = skill_dir.resolve()
        except OSError:
            logger.debug("failed resolving skill dir %s", skill_dir, exc_info=True)
            return None
        if not resolved.is_dir():
            return None
        return resolved
    return None


def list_workspace_skill_summaries(
    workspace_dir: Path,
    *,
    skills_disabled: set[str] | frozenset[str],
) -> list[dict[str, Any]]:
    """Scan ``skills/`` including symlinked directories outside the workspace."""
    skills_root = workspace_dir / _SKILLS_ROOT
    try:
        entries = list(skills_root.iterdir())
    except OSError:
        return []

    summaries: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda path: path.name):
        slug = entry.name
        if not slug or slug.startswith("."):
            continue
        skill_dir = _resolve_skill_dir(workspace_dir, slug)
        if skill_dir is None:
            continue
        manifest = _read_manifest(skill_dir)
        if manifest is None:
            continue
        meta, _body = parse_frontmatter(manifest)
        if meta.get("removed"):
            continue
        display_name = str(meta.get("name") or slug)
        summaries.append(
            _summary_dict(
                slug,
                meta,
                enabled=slug not in skills_disabled and display_name not in skills_disabled,
            )
        )
    return summaries


__all__ = ["list_workspace_skill_summaries"]
