"""Load workspace agent markdown files into deepagents ``SubAgent`` specs."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from deepagents import SubAgent

from octop_harness.backends.workspace import DEFAULT_AGENTS_DIR, BackendWorkspace

logger = logging.getLogger(__name__)

_README = "readme.md"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def parse_agent_frontmatter(text: str) -> tuple[dict[str, Any], str]:
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


def slug_from_agent_path(path_fragment: str) -> str:
    """Derive a stable subagent name from a workspace-relative ``.md`` path."""
    normalized = path_fragment.replace("\\", "/").rstrip("/")
    if normalized.lower().endswith(".md"):
        normalized = normalized[: -len(".md")]
    marker = f"/{DEFAULT_AGENTS_DIR}/"
    hay = normalized if normalized.startswith("/") else f"/{normalized}"
    idx = hay.find(marker)
    if idx != -1:
        normalized = hay[idx + len(marker) :]
    elif hay.rstrip("/") == f"/{DEFAULT_AGENTS_DIR}":
        normalized = ""
    parts = [_SLUG_RE.sub("-", part.lower()).strip("-") for part in normalized.split("/") if part]
    return "-".join(p for p in parts if p)


def agent_scan_roots(
    workspace: BackendWorkspace,
    *,
    extra: str | Path | Sequence[str | Path] | None = None,
) -> list[str]:
    """Return workspace-relative agent root fragments to scan."""
    roots: list[str] = []
    seen: set[str] = set()
    for fragment in workspace.system_read_roots(DEFAULT_AGENTS_DIR):
        if fragment in seen:
            continue
        seen.add(fragment)
        roots.append(fragment)
    if extra is None:
        return roots
    extras: list[str | Path] = [extra] if isinstance(extra, str | Path) else list(extra)
    for entry in extras:
        presented = workspace.present_path(workspace.resolve_path(str(entry)))
        if presented not in seen:
            seen.add(presented)
            roots.append(presented)
    return roots


def _ls_row(entry: Any) -> dict[str, Any]:
    if isinstance(entry, dict):
        return entry
    return {
        "path": getattr(entry, "path", None),
        "is_dir": getattr(entry, "is_dir", None),
    }


def collect_agent_markdown_paths(workspace: BackendWorkspace, root: str) -> list[str]:
    """Recursively list ``*.md`` under *root* (workspace-relative fragment)."""
    root_norm = root.rstrip("/") or "."
    found: list[str] = []

    def walk(dir_fragment: str) -> None:
        entries = workspace.list_dir(dir_fragment)
        if not entries:
            return
        for entry in entries:
            row = _ls_row(entry)
            rel_path = str(row.get("path") or "").replace("\\", "/").lstrip("/")
            if not rel_path:
                continue
            name = Path(rel_path).name
            if name.startswith("."):
                continue
            is_dir = row.get("is_dir")
            if is_dir is True:
                walk(rel_path)
                continue
            if is_dir is False and name.lower().endswith(".md"):
                if name.lower() == _README:
                    continue
                found.append(rel_path)
                continue
            if is_dir is None and not name.lower().endswith(".md"):
                walk(rel_path)

    walk(root_norm)
    return sorted(found)


def _parse_tools_meta(raw: Any) -> list[str] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in {"", "inherit", "default"}:
            return None
        return [raw.strip()]
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return None


def resolve_subagent_tools(
    tool_names: list[str] | None,
    *,
    parent_tools: Sequence[Any],
) -> list[Any] | None:
    """Map tool name strings to callables from the parent tool pool."""
    if tool_names is None:
        return None
    if not tool_names:
        return []
    by_name: dict[str, Any] = {}
    for tool in parent_tools:
        name = getattr(tool, "name", None)
        if name is not None:
            by_name[str(name)] = tool
    resolved: list[Any] = []
    for name in tool_names:
        tool = by_name.get(name)
        if tool is None:
            logger.warning("Unknown subagent tool %r; skipping", name)
            continue
        resolved.append(tool)
    return resolved


def parse_agent_markdown(
    text: str,
    *,
    path_fragment: str,
    parent_tools: Sequence[Any] | None = None,
    workspace: BackendWorkspace | None = None,
) -> SubAgent | None:
    """Parse agent markdown into a ``SubAgent`` dict, or ``None`` if invalid."""
    meta, body = parse_agent_frontmatter(text)
    if not meta:
        logger.warning("Skipping agent %s: missing YAML frontmatter", path_fragment)
        return None
    description = meta.get("description")
    if not description or not str(description).strip():
        logger.warning("Skipping agent %s: missing description", path_fragment)
        return None
    slug = str(meta.get("id") or slug_from_agent_path(path_fragment)).strip()
    if not slug:
        logger.warning("Skipping agent %s: empty subagent id", path_fragment)
        return None
    spec: SubAgent = {
        "name": slug,
        "description": str(description).strip(),
        "system_prompt": body.strip() or str(description).strip(),
    }
    model = meta.get("model")
    if model is not None and str(model).strip():
        spec["model"] = str(model).strip()
    skills_raw = meta.get("skills")
    if skills_raw is not None and workspace is not None:
        if isinstance(skills_raw, str):
            skills_raw = [skills_raw]
        if isinstance(skills_raw, list):
            spec["skills"] = [workspace.resolve_path(str(s)) for s in skills_raw if str(s).strip()]
    if parent_tools is not None:
        tools_meta = _parse_tools_meta(meta.get("tools"))
        resolved_tools = resolve_subagent_tools(tools_meta, parent_tools=parent_tools)
        if resolved_tools is not None:
            spec["tools"] = resolved_tools
    return spec


def load_subagents_from_workspace(
    workspace: BackendWorkspace,
    *,
    subagents_path: str | Path | Sequence[str | Path] | None = None,
    parent_tools: Sequence[Any] | None = None,
) -> list[SubAgent]:
    """Scan agent roots and return parsed ``SubAgent`` specs."""
    merged: dict[str, SubAgent] = {}
    seen_sources: set[str] = set()

    for root in agent_scan_roots(workspace, extra=subagents_path):
        for path_fragment in collect_agent_markdown_paths(workspace, root):
            # The legacy ``agents/`` root and the canonical prefixed root can
            # resolve to the same stored file (``.octop/agents/x.md``). Process
            # each file once so the name-merge below only warns on genuine
            # collisions between different files.
            source = workspace.resolve_path(path_fragment)
            if source in seen_sources:
                continue
            seen_sources.add(source)
            text = workspace.read_text(path_fragment)
            if text is None:
                continue
            spec = parse_agent_markdown(
                text,
                path_fragment=path_fragment,
                parent_tools=parent_tools,
                workspace=workspace,
            )
            if spec is None:
                continue
            name = spec["name"]
            if name in merged:
                logger.warning(
                    "Duplicate subagent name %r (%s); keeping later definition",
                    name,
                    path_fragment,
                )
            merged[name] = spec
    return list(merged.values())


def merge_subagents(
    loaded: Sequence[SubAgent],
    config_subagents: Sequence[SubAgent],
) -> list[SubAgent]:
    """Merge workspace-loaded subagents with config entries; config wins on name."""
    merged: dict[str, SubAgent] = {spec["name"]: spec for spec in loaded}
    for spec in config_subagents:
        merged[spec["name"]] = spec
    return list(merged.values())


__all__ = [
    "agent_scan_roots",
    "collect_agent_markdown_paths",
    "load_subagents_from_workspace",
    "merge_subagents",
    "parse_agent_frontmatter",
    "parse_agent_markdown",
    "resolve_subagent_tools",
    "slug_from_agent_path",
]
