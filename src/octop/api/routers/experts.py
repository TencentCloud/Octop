"""Experts router — bundled scene templates + SkillHub expert market.

GET  /api/experts                  → bundled expert summaries
GET  /api/experts/{id}             → template metadata + lazy ``file_contents``
POST /api/agents/from-expert/{id}  → create agent from bundled expert

GET  /api/experts/hub              → SkillHub market cards (``?q=&scene=``)
GET  /api/experts/hub/{slug}       → SkillHub market detail + quick prompts
POST /api/experts/hub/{slug}/install → create agent from market expert
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from octop.api.common.agent import require_agent_owner_row, user_owns_agent
from octop.api.common.agent_runtime import AgentRuntimeFields, runtime_field_updates
from octop.api.common.validators import assert_user_backend_root_dirs
from octop.api.deps import current_user, get_server
from octop.infra.agents.avatar import (
    display_published_expert_icon_url,
    public_portrait_icon_url,
    read_snapshot_avatar,
)
from octop.infra.agents.experts.catalog import (
    MANIFEST_FILENAME,
    apply_workspace_quick_prompts,
    build_create_spec_from_expert,
    discover_seed_paths,
    preview_file_paths,
    preview_paths_from_expert_dir,
    read_text_file_contents,
)
from octop.infra.agents.experts.composer_files import (
    ComposerApplyReport,
    ComposerSkillCopy,
    ComposerWorkspacePatch,
    apply_composer_workspace_patch,
    composer_plan_from_payload,
)
from octop.infra.agents.experts.market_creation import (
    SkillHubMarketAgentCreateOptions,
)
from octop.infra.agents.experts.market_creation import (
    create_agent_from_skillhub_skillset as create_skillhub_market_agent,
)
from octop.infra.agents.experts.published_creation import (
    PublishedExpertInstallOptions,
    require_published_expert,
    snapshot_welcome_payload,
)
from octop.infra.agents.experts.published_creation import (
    install_published_expert as install_published_expert_agent,
)
from octop.infra.agents.experts.published_creation import (
    publish_agent_expert as publish_owned_agent_expert,
)
from octop.infra.agents.experts.published_creation import (
    refresh_published_expert as refresh_owned_published_expert,
)
from octop.infra.agents.experts.published_creation import (
    unpublish_expert as unpublish_owned_expert,
)
from octop.infra.agents.experts.skillhub_market import (
    SkillHubMarketError,
    SkillHubMarketErrorKind,
    browse_skillsets,
    fetch_skillset,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.history.trajectory.settings import apply_enable_trajectory
from octop.infra.utils.locale import resolve_user_locale

router = APIRouter()


def _validated_session_defaults(
    registry: Any,
    user_id: int,
    *,
    knowledge_base_ids: list[str] | None,
    mcp_servers: list[str] | None,
) -> tuple[list[str] | None, list[str] | None]:
    kb_ids = (
        registry.validate_knowledge_base_ids(user_id, knowledge_base_ids)
        if knowledge_base_ids is not None
        else None
    )
    servers = (
        registry.validate_mcp_servers(user_id, mcp_servers) if mcp_servers is not None else None
    )
    return kb_ids, servers


_SAFE_MARKET_REASONS: dict[SkillHubMarketErrorKind, str] = {
    SkillHubMarketErrorKind.NOT_FOUND: "expert not found",
    SkillHubMarketErrorKind.INVALID_SLUG: "invalid expert id",
    SkillHubMarketErrorKind.UPSTREAM_TIMEOUT: "upstream timeout",
    SkillHubMarketErrorKind.UPSTREAM_BAD_PAYLOAD: "invalid upstream response",
    SkillHubMarketErrorKind.PACKAGE_INVALID: "invalid expert package",
    SkillHubMarketErrorKind.PACKAGE_TOO_LARGE: "expert package too large",
    SkillHubMarketErrorKind.UPSTREAM_FAILED: "upstream request failed",
    SkillHubMarketErrorKind.SSL_ERROR: "ssl error",
}


class ComposerFileOverrideBody(BaseModel):
    name: str
    content: str = ""


class ComposerHubSkillBody(BaseModel):
    skill_name: str
    display_name: str = ""
    icon_url: str = ""
    label: dict[str, str] | None = None
    summary: dict[str, str] | None = None


class ComposerCopySkillBody(BaseModel):
    agent_id: str
    slug: str


class FromExpertBody(AgentRuntimeFields):
    name: str | None = None
    description: str | None = None
    providers: list[str] | None = None
    default_model: str | None = None
    backend: dict[str, Any] | None = None
    skill_package_ids: list[str] | None = None
    knowledge_base_ids: list[str] | None = None
    mcp_servers: list[str] | None = None
    color: str | None = None
    agent_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional custom agent id; auto-generated when omitted",
    )
    welcome_message: str | None = None
    enable_trajectory: bool = True
    file_overrides: list[ComposerFileOverrideBody] | None = None
    omit_files: list[str] | None = None
    hub_skills: list[ComposerHubSkillBody] | None = None
    copy_skills: list[ComposerCopySkillBody] | None = None
    quick_prompts: list[QuickPromptResponse] | None = None


class PublishExpertBody(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    slug: str | None = None
    welcome_message: LocalizedTextResponse | None = None
    quick_prompts: list[QuickPromptResponse] | None = None


class RefreshPublishedExpertBody(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    welcome_message: LocalizedTextResponse | None = None
    quick_prompts: list[QuickPromptResponse] | None = None


class InstallPublishedExpertBody(AgentRuntimeFields):
    """Same create knobs as bundled / market experts, plus required name."""

    name: str = Field(min_length=1)
    description: str = ""
    providers: list[str] | None = None
    default_model: str | None = None
    backend: dict[str, Any] | None = None
    skill_package_ids: list[str] | None = None
    knowledge_base_ids: list[str] | None = None
    mcp_servers: list[str] | None = None
    color: str | None = None
    agent_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional custom agent id; auto-generated when omitted",
    )
    welcome_message: str | None = None
    enable_trajectory: bool = True
    file_overrides: list[ComposerFileOverrideBody] | None = None
    omit_files: list[str] | None = None
    hub_skills: list[ComposerHubSkillBody] | None = None
    copy_skills: list[ComposerCopySkillBody] | None = None
    quick_prompts: list[QuickPromptResponse] | None = None


def _composer_plan_from_body(
    body: FromExpertBody | InstallPublishedExpertBody,
) -> tuple[ComposerWorkspacePatch, tuple[ComposerSkillCopy, ...]]:
    return composer_plan_from_payload(
        file_overrides=[item.model_dump() for item in (body.file_overrides or [])],
        omit_files=body.omit_files,
        hub_skills=[item.model_dump() for item in (body.hub_skills or [])],
        copy_skills=[item.model_dump() for item in (body.copy_skills or [])],
    )


def _resolve_composer_copies(
    copies: tuple[ComposerSkillCopy, ...],
    *,
    user: Any,
    server: Any,
    report: ComposerApplyReport,
) -> tuple[tuple[str, Any], ...]:
    resolved: list[tuple[str, Any]] = []
    seen: set[str] = set()
    for item in copies:
        if item.slug in seen:
            continue
        seen.add(item.slug)
        try:
            require_agent_owner_row(item.agent_id, user=user, as_user=None, server=server)
        except OctopError:
            report.copy_skill_errors.append(item.slug)
            continue
        src = server.app_runtime.agent_registry.workspace_for_agent(item.agent_id)
        if src is None:
            report.copy_skill_errors.append(item.slug)
            continue
        resolved.append((item.slug, src))
    return tuple(resolved)


def _composer_apply(
    body: FromExpertBody | InstallPublishedExpertBody,
    *,
    user: Any,
    server: Any,
) -> tuple[ComposerWorkspacePatch, tuple[tuple[str, Any], ...], ComposerApplyReport]:
    patch, copies = _composer_plan_from_body(body)
    report = ComposerApplyReport()
    resolved = _resolve_composer_copies(copies, user=user, server=server, report=report)
    return patch, resolved, report


def _quick_prompts_from_body(
    body: FromExpertBody | InstallPublishedExpertBody,
) -> list[dict[str, Any]] | None:
    if body.quick_prompts is None:
        return None
    return [_quick_prompt_body_dict(item) for item in body.quick_prompts]


def _composer_initializer(
    patch: ComposerWorkspacePatch,
    copies: tuple[tuple[str, Any], ...] = (),
    report: ComposerApplyReport | None = None,
    quick_prompts: list[dict[str, Any]] | None = None,
) -> Any:
    if patch.is_empty() and not copies and quick_prompts is None:
        return None

    async def _apply(_row: Any, workspace: Any) -> None:
        if not patch.is_empty() or copies:
            await apply_composer_workspace_patch(workspace, patch, copies=copies, report=report)
        if quick_prompts is not None:
            await apply_workspace_quick_prompts(workspace, quick_prompts)

    return _apply


class LocalizedTextResponse(BaseModel):
    zh: str = ""
    en: str = ""


class QuickPromptResponse(BaseModel):
    title: LocalizedTextResponse
    description: LocalizedTextResponse
    prompt: LocalizedTextResponse
    color: str = "#e8f4ff"
    icon_name: str | None = None


class ExpertHubItemResponse(BaseModel):
    id: str
    slug: str
    label: LocalizedTextResponse
    description: LocalizedTextResponse
    scene: str = ""
    sub_scene: str = ""
    icon_url: str | None = None
    icon_name: str | None = None
    color: str | None = None
    skill_slugs: list[str] = Field(default_factory=list)
    skill_count: int = 0
    source: str = "skillhub"
    content: LocalizedTextResponse | None = None
    quick_prompts: list[QuickPromptResponse] | None = None
    task_examples: dict[str, list[str]] | None = None


class ExpertHubListResponse(BaseModel):
    items: list[ExpertHubItemResponse]
    scenes: list[str] = Field(default_factory=list)


class MarketCreateSourceResponse(BaseModel):
    source: str
    kind: str
    slug: str
    welcome_enrichment: str


class MarketCreateResponse(BaseModel):
    id: int | str
    agent_id: str
    user_id: int
    name: str
    description: str | None = None
    default_model: str | None = None
    state: str
    expert_id: str
    icon_name: str | None = None
    icon_url: str | None = None
    color: str | None = None
    market: MarketCreateSourceResponse
    bootstrap_pending: bool
    hub_skill_errors: list[str] = Field(default_factory=list)
    copy_skill_errors: list[str] = Field(default_factory=list)


def _quick_prompt_dict(p: Any) -> dict[str, Any]:
    return {
        "title": {"zh": p.title_zh, "en": p.title_en},
        "description": {"zh": p.description_zh, "en": p.description_en},
        "prompt": {"zh": p.prompt_zh, "en": p.prompt_en},
        "color": p.color,
        "icon_name": p.icon_name,
    }


def _quick_prompt_body_dict(p: QuickPromptResponse) -> dict[str, Any]:
    return {
        "title": {"zh": p.title.zh, "en": p.title.en},
        "description": {"zh": p.description.zh, "en": p.description.en},
        "prompt": {"zh": p.prompt.zh, "en": p.prompt.en},
        "color": p.color,
        "icon_name": p.icon_name,
    }


def _publish_welcome_fields(
    welcome: LocalizedTextResponse | None,
) -> tuple[str, str]:
    if welcome is None:
        return "", ""
    return welcome.zh, welcome.en


def _summary_dict(s: Any) -> dict[str, Any]:
    return {
        "id": s.id,
        "label": {"zh": s.label_zh, "en": s.label_en},
        "description": {"zh": s.description_zh, "en": s.description_en},
        "welcome_message": {
            "zh": s.welcome_message_zh,
            "en": s.welcome_message_en,
        },
        "icon_name": s.icon_name,
        "icon_url": getattr(s, "icon_url", None),
        "color": s.color,
        "quick_prompts": [_quick_prompt_dict(p) for p in getattr(s, "quick_prompts", ())],
        "task_examples": getattr(s, "task_examples", None),
    }


def _expert_dict(
    e: Any,
    catalog: Any,
    *,
    include_file_contents: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        **_summary_dict(e.summary),
        "files": list(e.files),
        "prompt_files": list(e.prompt_files),
        "quick_prompts": [_quick_prompt_dict(p) for p in getattr(e, "quick_prompts", ())],
    }
    if include_file_contents:
        result["file_contents"] = catalog.read_file_contents(
            e.summary.id,
            paths=preview_file_paths(e),
        )
    return result


def _map_skillhub_error(exc: SkillHubMarketError) -> OctopError:
    kind = getattr(exc, "kind", SkillHubMarketErrorKind.UPSTREAM_FAILED)
    if kind in (
        SkillHubMarketErrorKind.NOT_FOUND,
        SkillHubMarketErrorKind.INVALID_SLUG,
    ):
        return OctopError(ErrorCode.NOT_FOUND, "skillhub expert not found")
    if kind == SkillHubMarketErrorKind.SSL_ERROR:
        return OctopError(
            ErrorCode.SKILLHUB_SSL_FAILED,
            "skillhub ssl error",
            details={"reason": "ssl_error", "kind": kind.value},
        )
    reason = _SAFE_MARKET_REASONS.get(
        kind, _SAFE_MARKET_REASONS[SkillHubMarketErrorKind.UPSTREAM_FAILED]
    )
    return OctopError(
        ErrorCode.EXPERT_MARKET_FAILED,
        f"expert market failed: {reason}",
        details={"reason": reason, "kind": kind.value},
    )


def _published_snapshot_dir(server: Any, expert_id: str) -> Any:
    return server.services.paths.published_experts_dir / expert_id


def _published_creator_username(server: Any, created_by: str) -> str | None:
    try:
        user_id = int(created_by)
    except ValueError:
        return None
    user = server.services.user_repo.get(user_id)
    return user.username if user is not None else None


def _published_manifest_icon_url(snapshot_dir: Any) -> str | None:
    manifest_path = snapshot_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return public_portrait_icon_url(
        data.get("icon_url") if isinstance(data.get("icon_url"), str) else None
    )


def _published_summary_dict(row: Any, server: Any) -> dict[str, Any]:
    snapshot_dir = _published_snapshot_dir(server, row.id)
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "created_by": row.created_by,
        "creator_username": _published_creator_username(server, row.created_by),
        "source_agent_id": row.source_agent_id,
        "icon_name": row.icon_name or None,
        "icon_url": display_published_expert_icon_url(
            expert_id=row.id,
            snapshot_dir=snapshot_dir,
            updated_at=row.updated_at,
            fallback_icon_url=_published_manifest_icon_url(snapshot_dir),
        ),
        "color": row.color or None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _require_published_expert(server: Any, expert_id: str) -> Any:
    assert server.services is not None
    return require_published_expert(server.services, expert_id)


@router.get("/experts/published", summary="List published expert templates")
async def list_published_experts(
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """List expert snapshots published by users and available for private installation."""
    return [
        _published_summary_dict(row, server)
        for row in server.services.published_expert_repo.list_all()
    ]


@router.get(
    "/experts/published/{expert_id}/avatar",
    summary="Fetch published expert avatar",
)
async def get_published_expert_avatar(
    expert_id: str,
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Response:
    """Return the avatar bytes baked into the published snapshot, if any."""
    row = _require_published_expert(server, expert_id)
    found = read_snapshot_avatar(_published_snapshot_dir(server, row.id))
    if found is None:
        raise OctopError(ErrorCode.NOT_FOUND, "avatar not uploaded")
    data, media_type = found
    return Response(content=data, media_type=media_type)


@router.get("/experts/published/{expert_id}", summary="Get published expert template detail")
async def get_published_expert(
    expert_id: str,
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return published-expert metadata and a previewable snapshot file inventory."""
    row = _require_published_expert(server, expert_id)
    snapshot_dir = _published_snapshot_dir(server, row.id)
    preview_paths = await asyncio.to_thread(preview_paths_from_expert_dir, snapshot_dir)
    files = await asyncio.to_thread(discover_seed_paths, snapshot_dir)
    if (snapshot_dir / MANIFEST_FILENAME).is_file():
        files.insert(0, MANIFEST_FILENAME)
    welcome_payload = await asyncio.to_thread(snapshot_welcome_payload, snapshot_dir)
    return {
        **_published_summary_dict(row, server),
        "welcome_message": welcome_payload["welcome_message"],
        "quick_prompts": welcome_payload["quick_prompts"],
        "files": files,
        "file_contents": await asyncio.to_thread(
            read_text_file_contents,
            snapshot_dir,
            preview_paths,
        ),
    }


@router.post(
    "/agents/{agent_id}/publish-expert",
    status_code=201,
    summary="Publish an agent workspace as an expert template",
)
async def publish_agent_expert(
    agent_id: str,
    body: PublishExpertBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Snapshot an owned agent workspace into a globally installable expert template."""
    source = require_agent_owner_row(agent_id, user=user, as_user=None, server=server)
    if not user_owns_agent(source, user):
        raise OctopError(ErrorCode.FORBIDDEN, "agent not owned by user")
    assert server.app_runtime is not None
    assert server.services is not None
    workspace = server.app_runtime.agent_registry.workspace_for_agent(agent_id)
    if workspace is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    welcome_zh, welcome_en = _publish_welcome_fields(body.welcome_message)
    row = await publish_owned_agent_expert(
        services=server.services,
        registry=server.app_runtime.agent_registry,
        user=user,
        source=source,
        workspace=workspace,
        name=body.name,
        description=body.description,
        slug=body.slug,
        welcome_message_zh=welcome_zh,
        welcome_message_en=welcome_en,
        quick_prompts=tuple(_quick_prompt_body_dict(p) for p in (body.quick_prompts or [])),
    )
    return _published_summary_dict(row, server)


@router.post(
    "/experts/published/{expert_id}/refresh",
    summary="Refresh a published expert snapshot",
)
async def refresh_published_expert(
    expert_id: str,
    body: RefreshPublishedExpertBody | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Replace a published snapshot using its still-owned source agent workspace."""
    row = _require_published_expert(server, expert_id)
    if row.source_agent_id is None:
        raise OctopError(ErrorCode.NOT_FOUND, "published expert source agent not found")
    source = require_agent_owner_row(row.source_agent_id, user=user, as_user=None, server=server)
    assert server.app_runtime is not None
    assert server.services is not None
    workspace = server.app_runtime.agent_registry.workspace_for_agent(row.source_agent_id)
    if workspace is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {row.source_agent_id!r} not found")
    welcome_zh: str | None = None
    welcome_en: str | None = None
    quick_prompts: tuple[dict[str, Any], ...] | None = None
    if body is not None:
        if body.welcome_message is not None:
            welcome_zh, welcome_en = _publish_welcome_fields(body.welcome_message)
        if body.quick_prompts is not None:
            quick_prompts = tuple(_quick_prompt_body_dict(p) for p in body.quick_prompts)
    updated = await refresh_owned_published_expert(
        services=server.services,
        registry=server.app_runtime.agent_registry,
        user=user,
        expert_id=expert_id,
        source=source,
        workspace=workspace,
        name=body.name if body is not None else None,
        description=body.description if body is not None else None,
        welcome_message_zh=welcome_zh,
        welcome_message_en=welcome_en,
        quick_prompts=quick_prompts,
    )
    return _published_summary_dict(updated, server)


@router.delete(
    "/experts/published/{expert_id}",
    status_code=204,
    summary="Unpublish an expert template",
)
async def unpublish_expert(
    expert_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Response:
    """Remove a published expert's listing and snapshot without deleting installed forks."""
    assert server.services is not None
    await unpublish_owned_expert(services=server.services, user=user, expert_id=expert_id)
    return Response(status_code=204)


@router.post(
    "/experts/published/{expert_id}/install",
    status_code=201,
    summary="Install a private agent from a published expert",
)
async def install_published_expert(
    expert_id: str,
    body: InstallPublishedExpertBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create a private agent and seed it from the immutable published snapshot."""
    assert server.app_runtime is not None
    assert server.services is not None
    assert_user_backend_root_dirs(
        user,
        body.backend,
        policy_repo=server.services.user_policy_repo,
    )
    kb_ids, servers = _validated_session_defaults(
        server.app_runtime.agent_registry,
        user.id,
        knowledge_base_ids=body.knowledge_base_ids,
        mcp_servers=body.mcp_servers,
    )
    patch, copies, report = _composer_apply(body, user=user, server=server)
    result = await install_published_expert_agent(
        services=server.services,
        registry=server.app_runtime.agent_registry,
        user=user,
        expert_id=expert_id,
        options=PublishedExpertInstallOptions(
            name=body.name,
            description=body.description,
            providers=body.providers,
            default_model=body.default_model,
            backend=body.backend,
            skill_package_ids=body.skill_package_ids,
            knowledge_base_ids=kb_ids,
            mcp_servers=servers,
            color=body.color,
            agent_id=body.agent_id,
            welcome_message=body.welcome_message,
            runtime_config=runtime_field_updates(body, exclude_unset=True),
            enable_trajectory=body.enable_trajectory,
            workspace_patch=patch,
            composer_copies=copies,
            composer_report=report,
            quick_prompts=_quick_prompts_from_body(body),
        ),
    )
    result.update(report.as_api_fields())
    return result


@router.get("/experts")
async def list_experts(
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    catalog = server.expert_catalog
    if catalog is None:
        return []
    return [_summary_dict(s) for s in catalog.list_summaries()]


@router.get(
    "/experts/hub",
    response_model=ExpertHubListResponse,
    summary="List SkillHub expert market cards",
)
async def list_expert_hub(
    q: str = "",
    scene: str = "",
    _: Any = Depends(current_user),
) -> dict[str, Any]:
    """List SkillHub skillsets as market expert cards, optionally filtered by scene."""
    try:
        items, scenes = await asyncio.to_thread(browse_skillsets, q, scene=scene)
    except SkillHubMarketError as exc:
        raise _map_skillhub_error(exc) from exc
    return {
        "items": [item.api_dict(include_content=False) for item in items],
        "scenes": scenes,
    }


@router.get(
    "/experts/hub/{slug}",
    response_model=ExpertHubItemResponse,
    summary="Get SkillHub expert market detail",
)
async def get_expert_hub_item(
    slug: str,
    _: Any = Depends(current_user),
) -> dict[str, Any]:
    """SkillHub market detail, including workflow prompt and default quick prompts."""
    try:
        item = await asyncio.to_thread(fetch_skillset, slug)
    except SkillHubMarketError as exc:
        raise _map_skillhub_error(exc) from exc
    return item.api_dict(include_content=True)


@router.post(
    "/experts/hub/{slug}/install",
    status_code=201,
    response_model=MarketCreateResponse,
    summary="Create an agent from a SkillHub expert market card",
)
async def install_expert_hub_item(
    slug: str,
    body: FromExpertBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create an agent from a SkillHub skillset-backed expert template."""
    assert server.app_runtime is not None
    assert_user_backend_root_dirs(
        user,
        body.backend,
        policy_repo=server.services.user_policy_repo,
    )
    package_ids = (
        server.app_runtime.agent_registry.validate_skill_package_ids(body.skill_package_ids)
        if body.skill_package_ids is not None
        else None
    )
    if package_ids:
        server.app_runtime.agent_registry.assert_backend_supports_skill_packages(body.backend)
    kb_ids, servers = _validated_session_defaults(
        server.app_runtime.agent_registry,
        user.id,
        knowledge_base_ids=body.knowledge_base_ids,
        mcp_servers=body.mcp_servers,
    )
    patch, copies, report = _composer_apply(body, user=user, server=server)
    try:
        result = await create_skillhub_market_agent(
            server=server,
            user=user,
            slug=slug,
            options=SkillHubMarketAgentCreateOptions(
                name=body.name,
                description=body.description,
                providers=body.providers,
                default_model=body.default_model,
                backend=body.backend,
                color=body.color,
                agent_id=body.agent_id,
                welcome_message=body.welcome_message,
                skill_package_ids=package_ids,
                knowledge_base_ids=kb_ids,
                mcp_servers=servers,
                enable_trajectory=body.enable_trajectory,
                workspace_patch=patch,
                composer_copies=copies,
                composer_report=report,
                quick_prompts=_quick_prompts_from_body(body),
                **runtime_field_updates(body, exclude_unset=False),
            ),
        )
    except SkillHubMarketError as exc:
        raise _map_skillhub_error(exc) from exc

    row = result.row
    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "user_id": row.user_id,
        "name": row.name,
        "description": row.description,
        "default_model": row.default_model,
        "state": row.last_state or "unknown",
        "expert_id": result.expert_id,
        "icon_name": result.icon_name,
        "icon_url": getattr(row, "icon_url", None),
        "color": result.color,
        "market": {
            "source": "skillhub",
            "kind": "skillset",
            "slug": result.slug,
            "welcome_enrichment": result.welcome_enrichment,
        },
        "bootstrap_pending": not server.app_runtime.agent_registry.is_bootstrapped(row.agent_id),
        **report.as_api_fields(),
    }


@router.get("/experts/{expert_id}")
async def get_expert(
    expert_id: str,
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    catalog = server.expert_catalog
    expert = None if catalog is None else catalog.get(expert_id)
    if expert is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"expert {expert_id!r} not found")
    return _expert_dict(expert, catalog, include_file_contents=True)


@router.post("/agents/from-expert/{expert_id}", status_code=201)
async def create_agent_from_expert(
    expert_id: str,
    body: FromExpertBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create an agent with the expert template workspace files."""
    catalog = server.expert_catalog
    expert = None if catalog is None else catalog.get(expert_id)
    if expert is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"expert {expert_id!r} not found")
    assert server.app_runtime is not None
    assert_user_backend_root_dirs(
        user,
        body.backend,
        policy_repo=server.services.user_policy_repo,
    )
    package_ids = (
        server.app_runtime.agent_registry.validate_skill_package_ids(body.skill_package_ids)
        if body.skill_package_ids is not None
        else None
    )
    if package_ids:
        server.app_runtime.agent_registry.assert_backend_supports_skill_packages(body.backend)
    kb_ids, servers = _validated_session_defaults(
        server.app_runtime.agent_registry,
        user.id,
        knowledge_base_ids=body.knowledge_base_ids,
        mcp_servers=body.mcp_servers,
    )

    config_extra: dict[str, Any] = {}
    if body.providers:
        config_extra["providers"] = list(body.providers)
    if body.backend:
        config_extra["backend"] = body.backend
    apply_enable_trajectory(config_extra, body.enable_trajectory)

    locale = resolve_user_locale(
        user_repo=server.services.user_repo,
        user_id=user.id,
    )
    spec = build_create_spec_from_expert(
        expert_id=expert_id,
        expert=expert,
        user_id=user.id,
        name=body.name,
        description=body.description,
        locale=locale,
        default_model=body.default_model,
        config_extra=config_extra or None,
        runtime_config=runtime_field_updates(body, exclude_unset=True),
        agent_id=body.agent_id,
        color=body.color,
        welcome_message=body.welcome_message,
        skill_package_ids=package_ids,
        knowledge_base_ids=kb_ids,
        mcp_servers=servers,
    )
    patch, copies, report = _composer_apply(body, user=user, server=server)
    row = await server.app_runtime.agent_registry.create(
        spec,
        defer_bootstrap=True,
        workspace_initializer=_composer_initializer(
            patch,
            copies,
            report,
            quick_prompts=_quick_prompts_from_body(body),
        ),
    )
    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "user_id": row.user_id,
        "name": row.name,
        "description": row.description,
        "default_model": row.default_model,
        "state": row.last_state or "unknown",
        "expert_id": expert_id,
        "icon_name": row.icon_name or expert.summary.icon_name,
        "icon_url": row.icon_url,
        "color": row.color or expert.summary.color,
        "bootstrap_pending": not server.app_runtime.agent_registry.is_bootstrapped(row.agent_id),
        **report.as_api_fields(),
    }
