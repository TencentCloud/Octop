"""Scan workspace skill directories and return dashboard-friendly summaries."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from octop_harness.backends.workspace import BackendWorkspace

logger = logging.getLogger(__name__)

_BUILTIN_KIND = "builtin"
_WORKSPACE_KIND = "workspace"
_KIND_ORDER = {_BUILTIN_KIND: 0, _WORKSPACE_KIND: 1}
SKILL_PRESENTATION_METADATA_VERSION = 1


def skill_slug_from_path(path: str | None) -> str | None:
    """Extract the skill directory slug from a ``SKILL.md`` storage path."""
    if not path:
        return None
    normalized = str(path).replace("\\", "/").rstrip("/")
    if normalized.endswith("/SKILL.md"):
        normalized = normalized[: -len("/SKILL.md")]
    slug = normalized.rsplit("/", 1)[-1]
    return slug or None


def skill_identity_keys(skill: Mapping[str, Any]) -> set[str]:
    """Return slug and display-name keys used for disable / per-turn filters."""
    keys: set[str] = set()
    name = skill.get("name")
    if name is not None and str(name):
        keys.add(str(name))
    slug = skill.get("slug") or skill_slug_from_path(skill.get("path"))
    if slug:
        keys.add(slug)
    return keys


def is_skill_enabled(
    *,
    slug: str,
    display_name: str,
    skills_disabled: frozenset[str] | set[str],
) -> bool:
    return slug not in skills_disabled and display_name not in skills_disabled


def _parse_skill_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 4 :].lstrip("\n")
    try:
        meta = yaml.safe_load(raw) or {}
        if not isinstance(meta, dict):
            return {}, text
        return meta, body
    except yaml.YAMLError:
        return {}, text


def _summary_dict(
    slug: str,
    meta: dict[str, Any],
    *,
    enabled: bool,
    kind: str,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "slug": slug,
        "name": str(meta.get("name") or slug),
        "description": str(meta.get("description") or ""),
        "enabled": enabled,
        "kind": kind,
    }
    top_display = str(meta.get("display_name") or "").strip()
    if top_display:
        out["display_name"] = top_display
    metadata = meta.get("metadata") or {}
    if isinstance(metadata, dict):
        display_name = ""
        for key in ("octop", "harness", "lightclaw", "orca", "openclaw"):
            ext = metadata.get(key) or {}
            if not isinstance(ext, dict):
                continue
            if key == "octop":
                label = ext.get("label")
                short_summary = ext.get("summary")
                if isinstance(label, dict):
                    out["label"] = dict(label)
                if isinstance(short_summary, dict):
                    out["summary"] = dict(short_summary)
            if not display_name:
                display_name = str(ext.get("display_name") or "").strip()
            emoji = str(ext.get("emoji") or "").strip()
            if emoji and "emoji" not in out:
                out["emoji"] = emoji
            icon_url = str(ext.get("icon_url") or "").strip()
            parsed = urlparse(icon_url)
            if icon_url and "icon_url" not in out and parsed.scheme in {"http", "https"} and bool(parsed.netloc):
                out["icon_url"] = icon_url
        if display_name:
            out["display_name"] = display_name
    return out


async def _collect_skills_from_root(
    workspace: BackendWorkspace,
    root: str,
    *,
    kind: str,
    skills_disabled: frozenset[str],
) -> dict[str, dict[str, Any]]:
    result = await workspace.als(root)
    entries = list(getattr(result, "entries", None) or []) if result is not None else []
    out: dict[str, dict[str, Any]] = {}
    root_prefix = root.rstrip("/")
    for entry in entries:
        if isinstance(entry, dict):
            row = entry
        else:
            row = {
                "path": getattr(entry, "path", None),
                "is_dir": getattr(entry, "is_dir", None),
            }
        if not row.get("is_dir"):
            continue
        path = row.get("path") or ""
        slug = Path(str(path)).name
        if not slug or slug.startswith("."):
            continue
        try:
            manifest = await workspace.aread_text(f"{root_prefix}/{slug}/SKILL.md")
        except (OSError, UnicodeDecodeError, UnicodeError):
            logger.warning(
                "skipping skill %s under %s: failed to read SKILL.md",
                slug,
                root_prefix,
                exc_info=True,
            )
            continue
        if manifest is None:
            # Missing or undecodable (read_text fails soft on bad UTF-8).
            logger.warning(
                "skipping skill %s under %s: SKILL.md missing or unreadable",
                slug,
                root_prefix,
            )
            continue
        meta, _body = _parse_skill_frontmatter(manifest)
        if meta.get("removed"):
            continue
        display_name = str(meta.get("name") or slug)
        out[slug] = _summary_dict(
            slug,
            meta,
            enabled=is_skill_enabled(
                slug=slug,
                display_name=display_name,
                skills_disabled=skills_disabled,
            ),
            kind=kind,
        )
    return out


async def list_skill_summaries(
    workspace: BackendWorkspace,
    *,
    skills_disabled: frozenset[str] | set[str] | None = None,
    skills_dir: str | Path | Sequence[str | Path] | None = None,
) -> list[dict[str, Any]]:
    """Return installed skill summaries (builtin + workspace + extra dirs).

    Later roots win on slug collision (workspace overrides builtin; ``skills_dir``
    entries override both). Each ``skills_dir`` entry is a directory of skill
    folders, matching
    :meth:`~octop_harness.backends.workspace.BackendWorkspace.skill_paths`.

    Hosts that distinguish package-mounted skills (e.g. Octop) may relabel
    ``kind`` after the fact; this catalog only knows builtin vs workspace.
    """
    disabled = frozenset(str(x) for x in (skills_disabled or ()))
    merged: dict[str, dict[str, Any]] = {}
    for root, kind in workspace.skill_catalog_roots(extra=skills_dir):
        merged.update(
            await _collect_skills_from_root(
                workspace,
                root,
                kind=kind,
                skills_disabled=disabled,
            )
        )
    return sorted(
        merged.values(),
        key=lambda row: (_KIND_ORDER.get(str(row.get("kind")), 99), str(row.get("slug", ""))),
    )


__all__ = [
    "SKILL_PRESENTATION_METADATA_VERSION",
    "is_skill_enabled",
    "list_skill_summaries",
    "skill_identity_keys",
    "skill_slug_from_path",
]
