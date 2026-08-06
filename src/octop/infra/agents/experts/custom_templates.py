"""Publish an agent's reusable workspace assets as a custom expert template."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.agents.experts.catalog import MANIFEST_FILENAME, ExpertCatalog
from octop.infra.db.repos.agents import AgentRow
from octop.infra.errors import ErrorCode, OctopError

_TEMPLATE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_PROMPT_FILES = (
    "SOUL.md",
    "IDENTITY.md",
    "AGENTS.md",
    "BOOTSTRAP.md",
    "HEARTBEAT.md",
    "TOOLS.md",
)
_TEMPLATE_PREFIXES = ("skills/", "agents/")
_SKIP_PARTS = frozenset({".git", ".venv", "__pycache__", "node_modules"})
_SENSITIVE_PARTS = frozenset({"memory", "sessions", "inbound", "outbound"})
_SENSITIVE_NAMES = frozenset(
    {
        ".env",
        "user.md",
        "memory.md",
        "credentials.json",
        "secrets.json",
        "id_rsa",
        "id_ed25519",
        "memory.sqlite",
        "checkpoints.sqlite",
    }
)
_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
_MAX_FILE_BYTES = 10 * 1024 * 1024
_MAX_TEMPLATE_BYTES = 50 * 1024 * 1024
_MAX_TEMPLATE_FILES = 2_000


@dataclass(frozen=True)
class CustomExpertPublishSpec:
    template_id: str
    label_zh: str
    label_en: str
    description_zh: str = ""
    description_en: str = ""
    icon_name: str | None = None
    color: str | None = None


@dataclass(frozen=True)
class CustomExpertPreview:
    included_files: tuple[str, ...]
    excluded_sensitive_files: tuple[str, ...]
    ignored_file_count: int


@dataclass(frozen=True)
class CustomExpertPublishResult:
    template_id: str
    copied_files: tuple[str, ...]
    excluded_sensitive_files: tuple[str, ...]


def _match_path(item: Any, workspace: BackendWorkspace) -> str | None:
    if isinstance(item, dict):
        raw_path = item.get("path")
        is_dir = item.get("is_dir", False)
    else:
        raw_path = getattr(item, "path", None)
        is_dir = getattr(item, "is_dir", False)
    if not raw_path or is_dir:
        return None
    storage = str(raw_path).replace("\\", "/")
    ws_root = str(workspace.workspace_dir).replace("\\", "/").rstrip("/")
    if ws_root and storage.startswith(f"{ws_root}/"):
        storage = storage[len(ws_root) + 1 :]
    rel = storage.lstrip("/")
    parts = [part for part in rel.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def _is_sensitive(path: str) -> bool:
    parts = tuple(part.lower() for part in path.split("/"))
    name = parts[-1]
    return (
        any(part in _SKIP_PARTS for part in parts)
        or any(part in _SENSITIVE_PARTS for part in parts)
        or name in _SENSITIVE_NAMES
        or name.startswith(".env.")
        or name.endswith(_SENSITIVE_SUFFIXES)
    )


def _is_template_content(path: str) -> bool:
    return path in _PROMPT_FILES or path.startswith(_TEMPLATE_PREFIXES)


async def preview_custom_expert(workspace: BackendWorkspace) -> CustomExpertPreview:
    """Return the reusable files and blocked sensitive files in an agent workspace."""
    result = await workspace.aglob("**/*", ".")
    matches = [] if result is None else (getattr(result, "matches", None) or [])
    included: set[str] = set()
    excluded: set[str] = set()
    ignored = 0
    for item in matches:
        path = _match_path(item, workspace)
        if path is None:
            continue
        if path == MANIFEST_FILENAME:
            ignored += 1
        elif _is_sensitive(path):
            excluded.add(path)
        elif _is_template_content(path):
            included.add(path)
        else:
            ignored += 1
    return CustomExpertPreview(
        included_files=tuple(sorted(included)),
        excluded_sensitive_files=tuple(sorted(excluded)),
        ignored_file_count=ignored,
    )


async def _source_manifest(workspace: BackendWorkspace) -> dict[str, Any]:
    text = await workspace.aread_text(MANIFEST_FILENAME)
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _manifest(
    *,
    row: AgentRow,
    spec: CustomExpertPublishSpec,
    prompt_files: list[str],
    source_manifest: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": spec.template_id,
        "label": {"zh": spec.label_zh.strip(), "en": spec.label_en.strip()},
        "description": {
            "zh": spec.description_zh.strip(),
            "en": spec.description_en.strip(),
        },
        "prompt_files": prompt_files,
        "icon_name": spec.icon_name.strip() if spec.icon_name else None,
        "color": spec.color,
        "origin": {
            "kind": "organization_template",
            "published_at": datetime.now(UTC).isoformat(),
        },
    }
    welcome = source_manifest.get("welcome_message")
    if isinstance(welcome, (dict, str)):
        payload["welcome_message"] = welcome
    quick_prompts = source_manifest.get("quick_prompts")
    if isinstance(quick_prompts, list):
        payload["quick_prompts"] = quick_prompts
    defaults = {
        key: value
        for key, value in {
            "persona_mbti": row.persona_mbti,
            "system_prompt": row.system_prompt,
        }.items()
        if value
    }
    if defaults:
        payload["agent_defaults"] = defaults
    return payload


def _write_staged_template(
    temp_dir: Path,
    files: list[tuple[str, bytes]],
    manifest: dict[str, Any],
) -> None:
    for rel, blob in files:
        dest = temp_dir.joinpath(*rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
    (temp_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


async def publish_custom_expert(
    *,
    row: AgentRow,
    workspace: BackendWorkspace,
    catalog: ExpertCatalog,
    custom_root: Path,
    spec: CustomExpertPublishSpec,
) -> CustomExpertPublishResult:
    """Write a safe template snapshot and make it visible in the expert catalog."""
    if not _TEMPLATE_ID_RE.fullmatch(spec.template_id):
        raise OctopError(
            ErrorCode.EXPERT_TEMPLATE_INVALID,
            "template_id must use lowercase letters, numbers, and hyphens",
        )
    if not spec.label_zh.strip() or not spec.label_en.strip():
        raise OctopError(
            ErrorCode.EXPERT_TEMPLATE_INVALID,
            "both localized template labels are required",
        )
    if spec.color and not _COLOR_RE.fullmatch(spec.color):
        raise OctopError(
            ErrorCode.EXPERT_TEMPLATE_INVALID,
            "template color must be a six-digit hex color",
        )
    if catalog.get(spec.template_id) is not None:
        raise OctopError(
            ErrorCode.EXPERT_TEMPLATE_EXISTS,
            f"expert template {spec.template_id!r} already exists",
            details={"id": spec.template_id},
        )

    preview = await preview_custom_expert(workspace)
    if not preview.included_files:
        raise OctopError(
            ErrorCode.EXPERT_TEMPLATE_INVALID,
            "agent has no reusable prompt, skill, or subagent files",
        )
    if len(preview.included_files) > _MAX_TEMPLATE_FILES:
        raise OctopError(
            ErrorCode.EXPERT_TEMPLATE_INVALID,
            f"template has too many files (max {_MAX_TEMPLATE_FILES})",
        )

    files: list[tuple[str, bytes]] = []
    total_bytes = 0
    for path in preview.included_files:
        blob = await workspace.adownload_bytes(path)
        if blob is None:
            continue
        if len(blob) > _MAX_FILE_BYTES:
            raise OctopError(
                ErrorCode.EXPERT_TEMPLATE_INVALID,
                f"template file is too large: {path}",
                details={"path": path},
            )
        total_bytes += len(blob)
        if total_bytes > _MAX_TEMPLATE_BYTES:
            raise OctopError(
                ErrorCode.EXPERT_TEMPLATE_INVALID,
                "template content exceeds 50MB",
            )
        files.append((path, blob))
    if not files:
        raise OctopError(ErrorCode.EXPERT_TEMPLATE_INVALID, "template files could not be read")

    source_manifest = await _source_manifest(workspace)
    prompt_files = [name for name in _PROMPT_FILES if name in {path for path, _ in files}]
    manifest = _manifest(
        row=row,
        spec=spec,
        prompt_files=prompt_files,
        source_manifest=source_manifest,
    )

    await asyncio.to_thread(custom_root.mkdir, parents=True, exist_ok=True)
    target = custom_root / spec.template_id
    if await asyncio.to_thread(target.exists):
        raise OctopError(
            ErrorCode.EXPERT_TEMPLATE_EXISTS,
            f"expert template {spec.template_id!r} already exists",
            details={"id": spec.template_id},
        )
    temp_dir = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix=".publish-", dir=custom_root))
    moved = False
    try:
        await asyncio.to_thread(_write_staged_template, temp_dir, files, manifest)
        await asyncio.to_thread(temp_dir.replace, target)
        moved = True
        await asyncio.to_thread(catalog.refresh)
    except OSError as exc:
        if moved and await asyncio.to_thread(target.exists):
            await asyncio.to_thread(shutil.rmtree, target, True)
        raise OctopError(
            ErrorCode.EXPERT_TEMPLATE_PUBLISH_FAILED,
            "failed to write expert template",
        ) from exc
    finally:
        if not moved and await asyncio.to_thread(temp_dir.exists):
            await asyncio.to_thread(shutil.rmtree, temp_dir, True)

    return CustomExpertPublishResult(
        template_id=spec.template_id,
        copied_files=tuple(path for path, _ in files),
        excluded_sensitive_files=preview.excluded_sensitive_files,
    )


async def delete_custom_expert(
    *,
    template_id: str,
    catalog: ExpertCatalog,
    custom_root: Path,
) -> None:
    """Delete only an admin-published template, never bundled or market content."""
    expert = catalog.get(template_id)
    if expert is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"expert template {template_id!r} not found")
    if expert.summary.source != "custom":
        raise OctopError(ErrorCode.FORBIDDEN, "only custom expert templates can be deleted")
    target = catalog.expert_dir(template_id)
    root, resolved = await asyncio.gather(
        asyncio.to_thread(custom_root.resolve),
        asyncio.to_thread(target.resolve),
    )
    if resolved.parent != root:
        raise OctopError(ErrorCode.FORBIDDEN, "template is outside the custom expert directory")
    await asyncio.to_thread(shutil.rmtree, resolved)
    await asyncio.to_thread(catalog.refresh)
