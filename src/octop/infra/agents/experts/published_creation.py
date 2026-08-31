"""Publish / refresh / install / unpublish user expert templates."""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import IntegrityError as SqliteIntegrityError
from typing import Any, cast

from psycopg import IntegrityError as PsycopgIntegrityError

from octop.infra.agents.avatar import bind_workspace_avatar_icon_url
from octop.infra.agents.experts.catalog import MANIFEST_FILENAME, seed_expert_directory
from octop.infra.agents.experts.publish import (
    PublishedExpertSnapshotMeta,
    assert_can_mutate_published,
    export_agent_workspace_to_dir,
    resolve_published_expert_slug,
)
from octop.infra.agents.manager import AgentCreateSpec
from octop.infra.agents.memory_backend import (
    memory_config_for_choice,
    probe_memory_postgres_dsn,
)
from octop.infra.db.repos.published_experts import PublishedExpertRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import User
from octop.infra.utils.ulid import new_ulid


@dataclass(frozen=True)
class PublishedExpertInstallOptions:
    name: str
    description: str = ""
    providers: list[str] | None = None
    default_model: str | None = None
    backend: dict[str, Any] | None = None
    skill_package_ids: list[str] | None = None
    color: str | None = None
    agent_id: str | None = None
    icon_url: str | None = None
    welcome_message: str | None = None
    runtime_config: dict[str, Any] | None = None
    memory_backend: str | None = None
    memory_dsn: str | None = None


def _snapshot_dir(services: Any, expert_id: str) -> Path:
    return Path(services.paths.published_experts_dir) / expert_id


def _read_snapshot_manifest(snapshot_dir: Path) -> dict[str, Any]:
    manifest_path = snapshot_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _localized_text(node: Any, *, lang: str) -> str:
    if isinstance(node, dict):
        return str(node.get(lang) or node.get("zh" if lang == "zh" else "en") or "")
    if isinstance(node, str):
        return node
    return ""


def _manifest_welcome(manifest: dict[str, Any]) -> tuple[str, str]:
    welcome = manifest.get("welcome_message")
    return _localized_text(welcome, lang="zh"), _localized_text(welcome, lang="en")


def _manifest_quick_prompts(manifest: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    raw = manifest.get("quick_prompts")
    if not isinstance(raw, list):
        return ()
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
    return tuple(out)


def _agent_color(registry: Any, agent_id: str) -> str | None:
    row = registry.get_row(agent_id)
    if row is not None:
        color = str(getattr(row, "color", None) or "").strip()
        if color:
            return color
    cfg = registry.get_config(agent_id)
    color = cfg.get("color")
    return str(color).strip() if isinstance(color, str) and color.strip() else None


def _snapshot_meta(
    source: Any,
    *,
    name: str,
    description: str,
    color: str | None,
    welcome_message_zh: str = "",
    welcome_message_en: str = "",
    quick_prompts: tuple[dict[str, Any], ...] = (),
) -> PublishedExpertSnapshotMeta:
    return PublishedExpertSnapshotMeta(
        name=name,
        description=description,
        icon_name=(getattr(source, "icon_name", None) or source.icon or None),
        color=color,
        label_zh=name,
        label_en=name,
        welcome_message_zh=welcome_message_zh,
        welcome_message_en=welcome_message_en,
        quick_prompts=quick_prompts,
    )


def require_published_expert(services: Any, expert_id: str) -> PublishedExpertRow:
    row = services.published_expert_repo.get(expert_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"published expert {expert_id!r} not found")
    return cast(PublishedExpertRow, row)


def snapshot_welcome_message(snapshot_dir: Path) -> tuple[str, str]:
    return _manifest_welcome(_read_snapshot_manifest(snapshot_dir))


async def publish_agent_expert(
    *,
    services: Any,
    registry: Any,
    user: User,
    source: Any,
    workspace: Any,
    name: str,
    description: str = "",
    slug: str | None = None,
    welcome_message_zh: str = "",
    welcome_message_en: str = "",
    quick_prompts: tuple[dict[str, Any], ...] = (),
) -> PublishedExpertRow:
    """Snapshot an owned agent workspace into a globally installable expert template."""
    repo = services.published_expert_repo
    existing = repo.get_by_source_agent_id(source.agent_id)
    if existing is not None:
        raise OctopError.localized(
            ErrorCode.PUBLISHED_EXPERT_ALREADY_EXISTS,
            name=existing.name,
            details={"id": existing.id, "slug": existing.slug},
        )

    resolved_slug = resolve_published_expert_slug(repo=repo, name=name, slug=slug)
    expert_id = new_ulid()
    snapshot_dir = _snapshot_dir(services, expert_id)
    resolved_description = description or source.description or ""
    color = _agent_color(registry, source.agent_id) or ""
    icon_name = getattr(source, "icon_name", None) or source.icon or ""
    try:
        await export_agent_workspace_to_dir(
            workspace=workspace,
            dest=snapshot_dir,
            metadata=_snapshot_meta(
                source,
                name=name,
                description=resolved_description,
                color=color or None,
                welcome_message_zh=welcome_message_zh,
                welcome_message_en=welcome_message_en,
                quick_prompts=quick_prompts,
            ),
            manifest_id=resolved_slug,
        )
        return cast(
            PublishedExpertRow,
            repo.create(
                id=expert_id,
                slug=resolved_slug,
                name=name,
                description=resolved_description,
                created_by=str(user.id),
                source_agent_id=source.agent_id,
                icon_name=icon_name,
                color=color,
            ),
        )
    except (SqliteIntegrityError, PsycopgIntegrityError) as exc:
        await asyncio.to_thread(shutil.rmtree, snapshot_dir, ignore_errors=True)
        raise OctopError.localized(
            ErrorCode.PUBLISHED_EXPERT_SLUG_TAKEN,
            slug=resolved_slug,
            details={"slug": resolved_slug},
        ) from exc
    except Exception:
        await asyncio.to_thread(shutil.rmtree, snapshot_dir, ignore_errors=True)
        raise


async def refresh_published_expert(
    *,
    services: Any,
    registry: Any,
    user: User,
    expert_id: str,
    source: Any,
    workspace: Any,
    name: str | None = None,
    description: str | None = None,
    welcome_message_zh: str | None = None,
    welcome_message_en: str | None = None,
    quick_prompts: tuple[dict[str, Any], ...] | None = None,
) -> PublishedExpertRow:
    """Replace a published snapshot using its still-owned source agent workspace."""
    row = require_published_expert(services, expert_id)
    assert_can_mutate_published(row, user)
    if row.source_agent_id is None:
        raise OctopError(ErrorCode.NOT_FOUND, "published expert source agent not found")

    color = _agent_color(registry, source.agent_id) or ""
    icon_name = getattr(source, "icon_name", None) or source.icon or ""
    snapshot_dir = _snapshot_dir(services, row.id)
    existing_manifest = await asyncio.to_thread(_read_snapshot_manifest, snapshot_dir)
    existing_welcome_zh, existing_welcome_en = _manifest_welcome(existing_manifest)
    existing_quick_prompts = _manifest_quick_prompts(existing_manifest)
    resolved_name = name if name is not None else row.name
    resolved_description = description if description is not None else row.description
    resolved_welcome_zh = (
        welcome_message_zh if welcome_message_zh is not None else existing_welcome_zh
    )
    resolved_welcome_en = (
        welcome_message_en if welcome_message_en is not None else existing_welcome_en
    )
    resolved_quick_prompts = quick_prompts if quick_prompts is not None else existing_quick_prompts
    await export_agent_workspace_to_dir(
        workspace=workspace,
        dest=snapshot_dir,
        metadata=_snapshot_meta(
            source,
            name=resolved_name,
            description=resolved_description,
            color=color or None,
            welcome_message_zh=resolved_welcome_zh,
            welcome_message_en=resolved_welcome_en,
            quick_prompts=resolved_quick_prompts,
        ),
        manifest_id=row.slug,
    )
    return cast(
        PublishedExpertRow,
        services.published_expert_repo.update_snapshot_meta(
            row.id,
            icon_name=icon_name,
            color=color,
            name=resolved_name,
            description=resolved_description,
        ),
    )


async def unpublish_expert(*, services: Any, user: User, expert_id: str) -> None:
    """Remove a published expert's listing and snapshot without deleting installed forks."""
    row = require_published_expert(services, expert_id)
    assert_can_mutate_published(row, user)
    services.published_expert_repo.delete(row.id)
    await asyncio.to_thread(shutil.rmtree, _snapshot_dir(services, row.id), ignore_errors=True)


async def install_published_expert(
    *,
    services: Any,
    registry: Any,
    user: User,
    expert_id: str,
    options: PublishedExpertInstallOptions,
) -> dict[str, Any]:
    """Create a private agent and seed it from the immutable published snapshot."""
    row = require_published_expert(services, expert_id)
    snapshot_dir = _snapshot_dir(services, row.id)
    if not snapshot_dir.is_dir():
        raise OctopError(ErrorCode.NOT_FOUND, f"published expert {expert_id!r} snapshot not found")

    package_ids = (
        registry.validate_skill_package_ids(options.skill_package_ids)
        if options.skill_package_ids is not None
        else None
    )
    if package_ids:
        registry.assert_backend_supports_skill_packages(options.backend)

    config_extra: dict[str, Any] = {}
    if options.providers:
        config_extra["providers"] = list(options.providers)
    if options.backend:
        config_extra["backend"] = options.backend
    memory = memory_config_for_choice(
        options.memory_backend, services.config, dsn=options.memory_dsn
    )
    backend = memory.get("backend") if isinstance(memory, dict) else None
    raw_dsn = backend.get("dsn") if isinstance(backend, dict) else None
    if raw_dsn:
        probe_memory_postgres_dsn(str(raw_dsn))
    if memory:
        config_extra["memory"] = memory

    created = await registry.create(
        AgentCreateSpec(
            name=options.name,
            agent_id=options.agent_id,
            user_id=user.id,
            description=options.description or row.description,
            default_model=options.default_model,
            runtime_config=options.runtime_config or {},
            config=config_extra,
            template_name=None,
            icon_name=row.icon_name or None,
            icon_url=options.icon_url,
            color=options.color or row.color or None,
            published_expert_id=row.id,
            welcome_message=options.welcome_message,
        )
    )
    workspace = registry.workspace_for_agent(created.agent_id)
    if workspace is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {created.agent_id!r} not found")
    await seed_expert_directory(expert_dir=snapshot_dir, workspace=workspace)
    await bind_workspace_avatar_icon_url(registry, created.agent_id, workspace)
    if package_ids is not None:
        await registry.persist_skill_package_ids(created.agent_id, package_ids)
    await registry.reload(created.agent_id)
    return {
        "id": created.id,
        "agent_id": created.agent_id,
        "user_id": created.user_id,
        "name": created.name,
        "description": created.description,
        "default_model": created.default_model,
        "state": created.last_state or "unknown",
        "published_expert_id": row.id,
        "bootstrap_pending": not registry.is_bootstrapped(created.agent_id),
    }
