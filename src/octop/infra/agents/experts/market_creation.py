"""Create agents from octop.cloud expert market packages."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Literal

from octop.infra.agents.experts.avatar import materialize_remote_icon_url
from octop.infra.agents.experts.catalog import (
    apply_workspace_quick_prompts,
    build_create_spec_from_expert,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.history.trajectory.settings import apply_enable_trajectory
from octop.infra.market import PortalMarketError, install_portal_expert
from octop.infra.market.errors import local_network_error
from octop.infra.utils.locale import resolve_user_locale

logger = logging.getLogger(__name__)

WelcomeEnrichment = Literal["pending", "skipped", "succeeded", "failed"]


@dataclass(frozen=True)
class SkillHubMarketAgentCreateOptions:
    name: str | None = None
    description: str | None = None
    providers: list[str] | None = None
    default_model: str | None = None
    backend: dict[str, Any] | None = None
    color: str | None = None
    agent_id: str | None = None
    welcome_message: str | None = None
    skill_package_ids: list[str] | None = None
    knowledge_base_ids: list[str] | None = None
    mcp_servers: list[str] | None = None
    max_iters: int | None = None
    max_input_length: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    enable_trajectory: bool = True
    conversation_mode: str | None = None
    workspace_patch: Any = None
    composer_copies: tuple[tuple[str, Any], ...] = ()
    composer_report: Any = None
    quick_prompts: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class SkillHubMarketAgentCreateResult:
    row: Any
    expert_id: str
    icon_name: str | None
    color: str | None
    slug: str
    welcome_enrichment: WelcomeEnrichment
    source: str = "portal"
    kind: str = "library"


async def create_agent_from_skillhub_skillset(
    *,
    server: Any,
    user: Any,
    slug: str,
    options: SkillHubMarketAgentCreateOptions,
) -> SkillHubMarketAgentCreateResult:
    """Install an octop.cloud expert package and create an agent from it."""
    catalog = server.expert_catalog
    if catalog is None:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            "expert catalog is not available",
            status=503,
        )
    assert server.app_runtime is not None

    try:
        portal_install = await asyncio.to_thread(
            install_portal_expert,
            slug,
            server.paths.expert_market_dir,
        )
    except PortalMarketError as exc:
        logger.warning("portal expert install failed slug=%s", slug, exc_info=True)
        network_error = local_network_error(exc)
        if network_error is not None:
            raise network_error from exc
        raise OctopError(
            ErrorCode.EXPERT_MARKET_FAILED,
            "expert market package failed",
            details={"reason": "package_invalid"},
        ) from exc

    if portal_install is None:
        raise OctopError(ErrorCode.NOT_FOUND, "expert not found")
    expert_id = portal_install.expert_id
    market_slug = portal_install.slug
    source = "portal"
    kind = "library"

    catalog.refresh()
    expert = catalog.get(expert_id)
    if expert is None:
        raise OctopError(
            ErrorCode.EXPERT_MARKET_FAILED,
            "expert market package failed",
            details={"reason": "package_invalid"},
        )

    welcome_enrichment: WelcomeEnrichment = "skipped"

    config_extra: dict[str, Any] = {
        "expert_source": {
            "type": source,
            "kind": kind,
            "slug": market_slug,
            "welcome_enrichment": welcome_enrichment,
        }
    }
    if options.providers:
        config_extra["providers"] = list(options.providers)
    if options.backend:
        config_extra["backend"] = options.backend
    apply_enable_trajectory(config_extra, options.enable_trajectory)
    if options.conversation_mode:
        config_extra["conversation_mode"] = options.conversation_mode

    locale = resolve_user_locale(
        user_repo=server.services.user_repo,
        user_id=user.id,
    )
    customized_welcome = options.welcome_message is not None
    portrait_url = portal_install.icon_url or expert.summary.icon_url
    spec = build_create_spec_from_expert(
        expert_id=expert_id,
        expert=expert,
        user_id=user.id,
        name=options.name,
        description=options.description,
        locale=locale,
        default_model=options.default_model,
        config_extra=config_extra,
        agent_id=options.agent_id,
        runtime_config={
            key: value
            for key, value in {
                "max_iters": options.max_iters,
                "max_input_length": options.max_input_length,
                "temperature": options.temperature,
                "top_p": options.top_p,
                "max_tokens": options.max_tokens,
            }.items()
            if value is not None
        },
        icon_url=portrait_url,
        color=options.color,
        welcome_message=(options.welcome_message if customized_welcome else None),
        skill_package_ids=options.skill_package_ids,
        knowledge_base_ids=options.knowledge_base_ids,
        mcp_servers=options.mcp_servers,
    )
    registry = server.app_runtime.agent_registry

    async def apply_patch(_row: Any, workspace: Any) -> None:
        from octop.infra.agents.experts.composer_files import (
            ComposerWorkspacePatch,
            apply_composer_workspace_patch,
        )

        patch = options.workspace_patch
        need_composer = (
            patch is not None and not getattr(patch, "is_empty", lambda: True)()
        ) or bool(options.composer_copies)
        if need_composer:
            await apply_composer_workspace_patch(
                workspace,
                patch if patch is not None else ComposerWorkspacePatch(),
                copies=options.composer_copies,
                report=options.composer_report,
            )
        if options.quick_prompts is not None:
            await apply_workspace_quick_prompts(workspace, options.quick_prompts)

    patch = options.workspace_patch
    need_apply = (
        (patch is not None and not getattr(patch, "is_empty", lambda: True)())
        or bool(options.composer_copies)
        or options.quick_prompts is not None
    )
    row = await registry.create(
        spec,
        defer_bootstrap=True,
        workspace_initializer=apply_patch if need_apply else None,
    )

    workspace = registry.workspace_for_agent(row.agent_id)
    if workspace is not None:
        from octop.infra.agents.experts.supplements import append_supplements  # noqa: PLC0415

        await append_supplements(workspace)
    if workspace is not None and portrait_url:
        try:
            await materialize_remote_icon_url(
                registry,
                row.agent_id,
                workspace,
                portrait_url,
            )
        except Exception:
            logger.warning(
                "market avatar materialize failed agent=%s slug=%s",
                row.agent_id,
                market_slug,
                exc_info=True,
            )

    return SkillHubMarketAgentCreateResult(
        row=row,
        expert_id=expert_id,
        icon_name=expert.summary.icon_name,
        color=options.color or expert.summary.color,
        slug=market_slug,
        welcome_enrichment=welcome_enrichment,
        source=source,
        kind=kind,
    )
