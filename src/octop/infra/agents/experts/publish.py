"""Export agent workspaces as installable published-expert snapshots."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.agents.avatar import copy_workspace_avatar_to_dir
from octop.infra.agents.builtin_skills import OCTOP_BUILTIN_SKILLS_ROOT
from octop.infra.agents.experts.catalog import MANIFEST_FILENAME
from octop.infra.agents.subagents.catalog import slugify
from octop.infra.db.repos.published_experts import PublishedExpertRepo, PublishedExpertRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import User

_EXCLUDED_PARTS = frozenset(
    {
        ".git",
        "__pycache__",
        ".harness-materialize",
        OCTOP_BUILTIN_SKILLS_ROOT,
        # Runtime / user-session data — never seed into published templates.
        "inbound",
        "daily",
        "uploads",
        "sessions",
        "media",
        "logs",
    }
)
_EXCLUDED_FILENAMES = frozenset({".env", "credentials.json"})
_MEMORY_SQLITE_PREFIX = "memory.sqlite"
_EXPORT_ROOT_MD = frozenset(
    {
        "SOUL.md",
        "IDENTITY.md",
        "USER.md",
        "AGENTS.md",
        "TOOLS.md",
        "HEARTBEAT.md",
        "PROACTIVE.md",
    }
)
_SEEDABLE_GLOB_PATTERNS = ("*.md", "skills/**/*", "agents/*.md")


@dataclass(frozen=True)
class PublishedExpertSnapshotMeta:
    name: str
    description: str
    icon_name: str | None
    color: str | None
    label_zh: str
    label_en: str
    welcome_message_zh: str
    welcome_message_en: str
    quick_prompts: tuple[dict[str, Any], ...] = ()


def assert_can_mutate_published(row: PublishedExpertRow, user: User) -> None:
    """Allow a published expert's creator or an administrator to mutate it."""
    if user.is_admin or str(user.id) == row.created_by:
        return
    raise OctopError(ErrorCode.FORBIDDEN, "published expert can only be modified by its creator")


def resolve_published_expert_slug(
    *,
    repo: PublishedExpertRepo,
    name: str,
    slug: str | None = None,
) -> str:
    """Return a unique derived slug or reject an already-requested explicit slug."""
    requested_slug = (slug or "").strip()
    requested = requested_slug or slugify(name) or "expert"
    if requested_slug:
        if repo.get_by_slug(requested) is not None:
            raise OctopError.localized(
                ErrorCode.PUBLISHED_EXPERT_SLUG_TAKEN,
                slug=requested,
                details={"slug": requested},
            )
        return requested

    candidate = requested
    suffix = 2
    while repo.get_by_slug(candidate) is not None:
        candidate = f"{requested}-{suffix}"
        suffix += 1
    return candidate


async def export_agent_workspace_to_dir(
    *,
    workspace: BackendWorkspace,
    dest: Path,
    metadata: PublishedExpertSnapshotMeta | None = None,
    manifest_id: str | None = None,
) -> list[str]:
    """Atomically replace *dest* with exported workspace files."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=f".{dest.name}.", dir=dest.parent))
    try:
        exported = await _write_workspace_snapshot(
            workspace=workspace,
            dest=staging_dir,
            metadata=metadata,
            manifest_id=manifest_id or dest.name,
        )
        _replace_snapshot_dir(staging_dir, dest)
    except BaseException:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    return exported


async def _write_workspace_snapshot(
    *,
    workspace: BackendWorkspace,
    dest: Path,
    metadata: PublishedExpertSnapshotMeta | None,
    manifest_id: str,
) -> list[str]:
    """Copy seedable workspace files into an empty staging directory."""
    paths = await _workspace_file_paths(workspace)
    dest.mkdir(parents=True, exist_ok=True)

    exported: list[str] = []
    for rel in paths:
        if not _is_seedable_path(rel):
            continue
        if rel == MANIFEST_FILENAME:
            continue
        content = await workspace.adownload_bytes(rel)
        if content is None:
            continue
        target = dest.joinpath(*PurePosixPath(rel).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        exported.append(rel)

    avatar_rel = await copy_workspace_avatar_to_dir(workspace, dest)
    if avatar_rel:
        exported.append(avatar_rel)

    prompt_files = sorted(rel for rel in exported if "/" not in rel and rel.endswith(".md"))
    if metadata is not None:
        manifest = _manifest_from_metadata(
            metadata,
            manifest_id=manifest_id,
            prompt_files=prompt_files,
        )
    else:
        raw_manifest = await workspace.adownload_bytes(MANIFEST_FILENAME)
        if raw_manifest is None:
            raise ValueError(f"workspace does not contain {MANIFEST_FILENAME}")
        _validate_manifest(raw_manifest)
        manifest = raw_manifest

    manifest_path = dest / MANIFEST_FILENAME
    manifest_path.write_bytes(manifest)
    exported.append(MANIFEST_FILENAME)
    return sorted(exported)


def _replace_snapshot_dir(staging_dir: Path, dest: Path) -> None:
    """Swap a completed staging directory into place, restoring on failure."""
    backup_dir = dest.with_name(f".{dest.name}.previous-{uuid4().hex}")

    moved_existing = dest.exists()
    if moved_existing:
        os.replace(dest, backup_dir)
    try:
        os.replace(staging_dir, dest)
    except BaseException:
        if moved_existing and not dest.exists():
            os.replace(backup_dir, dest)
        raise
    if moved_existing:
        shutil.rmtree(backup_dir, ignore_errors=True)


def _manifest_from_metadata(
    metadata: PublishedExpertSnapshotMeta,
    *,
    manifest_id: str,
    prompt_files: list[str] | None = None,
) -> bytes:
    """Build snapshot manifest from publish metadata only — never copy workspace manifest."""
    data: dict[str, Any] = {
        "id": manifest_id,
        "label": {"zh": metadata.label_zh, "en": metadata.label_en},
        "description": {"zh": metadata.description, "en": metadata.description},
        "welcome_message": {
            "zh": metadata.welcome_message_zh,
            "en": metadata.welcome_message_en,
        },
    }
    if prompt_files:
        data["prompt_files"] = prompt_files
    if metadata.icon_name:
        data["icon_name"] = metadata.icon_name
    if metadata.color:
        data["color"] = metadata.color
    if metadata.quick_prompts:
        data["quick_prompts"] = list(metadata.quick_prompts)
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def _validate_manifest(content: bytes | None) -> None:
    if content is None:
        raise ValueError(f"workspace does not contain {MANIFEST_FILENAME}")
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"{MANIFEST_FILENAME} must be a valid JSON object") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{MANIFEST_FILENAME} must be a valid JSON object")


async def _workspace_file_paths(workspace: BackendWorkspace) -> list[str]:
    """List candidate workspace files for expert-template export."""
    paths: set[str] = set()
    for pattern in _SEEDABLE_GLOB_PATTERNS:
        result = await workspace.aglob(pattern)
        if result is None:
            raise RuntimeError("workspace backend cannot list files for snapshot export")
        for entry in result.matches or []:
            if isinstance(entry, dict):
                is_dir = bool(entry.get("is_dir", False))
                path = entry.get("path")
            else:
                is_dir = bool(getattr(entry, "is_dir", False))
                path = getattr(entry, "path", None)
            if is_dir:
                continue
            if not isinstance(path, str):
                continue
            rel = path.replace("\\", "/").lstrip("/")
            if rel and rel != ".":
                paths.add(rel)
    return sorted(paths)


def _is_seedable_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if not parts or any(part in _EXCLUDED_PARTS or part.startswith(".") for part in parts):
        return False
    basename = parts[-1]
    if basename in _EXCLUDED_FILENAMES:
        return False
    if basename.startswith(_MEMORY_SQLITE_PREFIX):
        return False
    if len(parts) == 1:
        return basename in _EXPORT_ROOT_MD
    if parts[0] == "skills":
        return True
    if parts[0] == "agents":
        return basename.endswith(".md")
    return False
