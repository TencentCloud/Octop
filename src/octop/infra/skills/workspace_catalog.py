"""Symlink-tolerant workspace skill discovery for Octop."""

from __future__ import annotations

import logging
import stat
from pathlib import Path
from typing import Any

from octop.infra.agents.workspace_dir import skills_discovery_roots
from octop.infra.skills.presentation import apply_skill_presentation
from octop.infra.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


def _summary_dict(
    slug: str,
    meta: dict[str, Any],
    *,
    enabled: bool,
) -> dict[str, Any]:
    return apply_skill_presentation(
        {
            "slug": slug,
            "name": str(meta.get("name") or slug),
            "description": str(meta.get("description") or ""),
            "enabled": enabled,
            "kind": "workspace",
        },
        meta,
    )


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


def _skills_roots(workspace_dir: Path) -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()
    for root in skills_discovery_roots(workspace_dir):
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved in seen or not root.is_dir():
            continue
        seen.add(resolved)
        roots.append(root)
    return roots


def _resolve_skill_dir(workspace_dir: Path, slug: str) -> Path | None:
    for skills_root in _skills_roots(workspace_dir):
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


def list_workspace_skill_summaries(
    workspace_dir: Path,
    *,
    skills_disabled: set[str] | frozenset[str],
) -> list[dict[str, Any]]:
    """Scan ``skills/`` including ``.octop/skills`` and symlinked directories."""
    seen: set[str] = set()
    summaries: list[dict[str, Any]] = []
    for skills_root in _skills_roots(workspace_dir):
        try:
            entries = list(skills_root.iterdir())
        except OSError:
            continue
        for entry in sorted(entries, key=lambda path: path.name):
            slug = entry.name
            if not slug or slug.startswith(".") or slug in seen:
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
            seen.add(slug)
            summaries.append(
                _summary_dict(
                    slug,
                    meta,
                    enabled=slug not in skills_disabled and display_name not in skills_disabled,
                )
            )
    return summaries


__all__ = ["list_workspace_skill_summaries"]
