"""Summaries of workspace subagents for dashboards and tooling."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from octop_harness.backends.workspace import BackendWorkspace
from octop_harness.subagents.loader import (
    agent_scan_roots,
    collect_agent_markdown_paths,
    parse_agent_frontmatter,
    slug_from_agent_path,
)

# Fallback when frontmatter omits ``emoji`` (matches dashboard UI default).
DEFAULT_SUBAGENT_EMOJI = "🤖"


async def list_subagent_summaries(
    workspace: BackendWorkspace,
    *,
    subagents_path: str | Path | Sequence[str | Path] | None = None,
) -> list[dict[str, Any]]:
    """Return installed subagent summaries from workspace markdown files."""
    merged: dict[str, dict[str, Any]] = {}

    for root in agent_scan_roots(workspace, extra=subagents_path):
        # Recursive listing stays sync (same helper as graph compile); off the
        # event loop so remote backends do not block. Manifest reads use
        # ``aread_text`` like :func:`octop_harness.skills.catalog.list_skill_summaries`.
        paths = await asyncio.to_thread(collect_agent_markdown_paths, workspace, root)
        for path_fragment in paths:
            text = await workspace.aread_text(path_fragment)
            if text is None:
                continue
            meta, _ = parse_agent_frontmatter(text)
            description = meta.get("description")
            if not description or not str(description).strip():
                continue
            slug = str(meta.get("id") or slug_from_agent_path(path_fragment)).strip()
            display_name = str(meta.get("name") or slug)
            emoji = str(meta.get("emoji") or "").strip() or DEFAULT_SUBAGENT_EMOJI
            merged[slug] = {
                "slug": slug,
                "name": display_name,
                "description": str(description).strip(),
                "path": path_fragment,
                "emoji": emoji,
            }
    return sorted(merged.values(), key=lambda row: str(row.get("slug", "")))


__all__ = ["DEFAULT_SUBAGENT_EMOJI", "list_subagent_summaries"]
