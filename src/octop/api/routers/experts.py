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
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import current_admin, current_user, get_server
from octop.infra.agents.experts.catalog import (
    build_create_spec_from_expert,
    preview_file_paths,
)
from octop.infra.agents.experts.market_creation import (
    SkillHubMarketAgentCreateOptions,
)
from octop.infra.agents.experts.market_creation import (
    create_agent_from_skillhub_skillset as create_skillhub_market_agent,
)
from octop.infra.agents.experts.skillhub_market import (
    SkillHubMarketError,
    SkillHubMarketErrorKind,
    browse_skillsets,
    fetch_skillset,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.locale import resolve_user_locale

router = APIRouter()
admin_router = APIRouter()

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


class FromExpertBody(BaseModel):
    name: str | None = None
    description: str | None = None
    providers: list[str] | None = None
    default_model: str | None = None
    backend: dict[str, Any] | None = None
    skill_package_ids: list[str] | None = None


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
    color: str | None = None
    market: MarketCreateSourceResponse
    bootstrap_pending: bool


class CustomExpertPreviewResponse(BaseModel):
    included_files: list[str]
    excluded_sensitive_files: list[str]
    ignored_file_count: int


class CustomExpertPublishBody(BaseModel):
    template_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]{0,63}$",
        description="Stable organization template id using lowercase letters, digits, and hyphens",
    )
    label_zh: str = Field(min_length=1, max_length=100)
    label_en: str = Field(min_length=1, max_length=100)
    description_zh: str = Field(default="", max_length=500)
    description_en: str = Field(default="", max_length=500)
    icon_name: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class CustomExpertPublishResponse(BaseModel):
    template_id: str
    copied_files: list[str]
    excluded_sensitive_files: list[str]


def _quick_prompt_dict(p: Any) -> dict[str, Any]:
    return {
        "title": {"zh": p.title_zh, "en": p.title_en},
        "description": {"zh": p.description_zh, "en": p.description_en},
        "prompt": {"zh": p.prompt_zh, "en": p.prompt_en},
        "color": p.color,
        "icon_name": p.icon_name,
    }


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
        "color": s.color,
        "source": getattr(s, "source", "bundled"),
        "quick_prompts": [_quick_prompt_dict(p) for p in getattr(s, "quick_prompts", ())],
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


@admin_router.get(
    "/agents/{agent_id}/expert-template/preview",
    response_model=CustomExpertPreviewResponse,
    summary="Preview reusable files for an organization expert template",
)
async def preview_agent_expert_template(
    agent_id: str,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """List the reusable workspace files and sensitive files that will be excluded."""
    assert server.app_runtime is not None
    preview = await server.app_runtime.agent_registry.preview_expert_template(agent_id)
    return {
        "included_files": list(preview.included_files),
        "excluded_sensitive_files": list(preview.excluded_sensitive_files),
        "ignored_file_count": preview.ignored_file_count,
    }


@admin_router.post(
    "/agents/{agent_id}/expert-template",
    status_code=201,
    response_model=CustomExpertPublishResponse,
    summary="Publish an agent as an organization expert template",
)
async def publish_agent_expert_template(
    agent_id: str,
    body: CustomExpertPublishBody,
    admin: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Snapshot prompts, skills, and subagents; runtime state and secrets are excluded."""
    from octop.infra.agents.experts.custom_templates import (  # noqa: PLC0415
        CustomExpertPublishSpec,
    )

    assert server.app_runtime is not None
    result = await server.app_runtime.agent_registry.publish_expert_template(
        agent_id,
        CustomExpertPublishSpec(**body.model_dump()),
        actor=admin.username,
    )
    return {
        "template_id": result.template_id,
        "copied_files": list(result.copied_files),
        "excluded_sensitive_files": list(result.excluded_sensitive_files),
    }


@admin_router.delete(
    "/expert-templates/{template_id}",
    status_code=204,
    summary="Delete an organization expert template",
)
async def delete_expert_template(
    template_id: str,
    admin: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> None:
    """Delete only the reusable template; agents previously created from it remain intact."""
    assert server.app_runtime is not None
    await server.app_runtime.agent_registry.delete_expert_template(
        template_id,
        actor=admin.username,
    )


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
    package_ids = (
        server.app_runtime.agent_registry.validate_skill_package_ids(body.skill_package_ids)
        if body.skill_package_ids is not None
        else None
    )
    if package_ids:
        server.app_runtime.agent_registry.assert_backend_supports_skill_packages(body.backend)
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
            ),
        )
    except SkillHubMarketError as exc:
        raise _map_skillhub_error(exc) from exc

    row = result.row
    if package_ids is not None:
        await server.app_runtime.agent_registry.persist_skill_package_ids(row.agent_id, package_ids)
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
        "color": result.color,
        "market": {
            "source": "skillhub",
            "kind": "skillset",
            "slug": result.slug,
            "welcome_enrichment": result.welcome_enrichment,
        },
        "bootstrap_pending": not server.app_runtime.agent_registry.is_bootstrapped(row.agent_id),
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
    package_ids = (
        server.app_runtime.agent_registry.validate_skill_package_ids(body.skill_package_ids)
        if body.skill_package_ids is not None
        else None
    )
    if package_ids:
        server.app_runtime.agent_registry.assert_backend_supports_skill_packages(body.backend)

    config_extra: dict[str, Any] = {}
    if body.providers:
        config_extra["providers"] = list(body.providers)
    if body.backend:
        config_extra["backend"] = body.backend

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
    )
    row = await server.app_runtime.agent_registry.create(spec, defer_bootstrap=True)
    if package_ids is not None:
        await server.app_runtime.agent_registry.persist_skill_package_ids(row.agent_id, package_ids)
    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "user_id": row.user_id,
        "name": row.name,
        "description": row.description,
        "default_model": row.default_model,
        "state": row.last_state or "unknown",
        "expert_id": expert_id,
        "icon_name": expert.summary.icon_name,
        "color": expert.summary.color,
        "bootstrap_pending": not server.app_runtime.agent_registry.is_bootstrapped(row.agent_id),
    }
