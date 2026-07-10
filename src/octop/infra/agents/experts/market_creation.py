"""Create agents from SkillHub-backed expert market templates."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from octop.infra.agents.experts.catalog import build_create_spec_from_expert
from octop.infra.agents.experts.manifest_generator import (
    generate_and_apply_skillhub_manifest_assets,
)
from octop.infra.agents.experts.skillhub_market import (
    SkillHubMarketError,
    install_skillset_template,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.locale import resolve_user_locale

logger = logging.getLogger(__name__)

_SKILLHUB_MANIFEST_GENERATION_TIMEOUT_SECONDS = 45.0
_GENERATOR_LIGHTWEIGHT_MODEL_HINTS = (
    "flash",
    "mini",
    "m3",
    "turbo",
    "haiku",
    "lite",
    "small",
)


@dataclass(frozen=True)
class SkillHubMarketAgentCreateOptions:
    name: str | None = None
    description: str | None = None
    providers: list[str] | None = None
    default_model: str | None = None
    backend: dict[str, Any] | None = None


@dataclass(frozen=True)
class SkillHubMarketAgentCreateResult:
    row: Any
    expert_id: str
    icon_name: str | None
    color: str | None
    slug: str
    quick_prompts_generated: bool


def _resolve_generator_model_ref(server: Any, requested_model: str | None) -> str | None:
    """Pick a usable model for internal manifest generation."""
    assert server.app_runtime is not None
    registry = server.app_runtime.agent_registry
    providers = registry.providers
    requested = (requested_model or "").strip()
    if requested and providers.is_model_ref_usable(requested):
        return requested

    active_name, active_model = server.services.settings_repo.get_active_model()
    active_ref = f"{active_name}/{active_model}" if active_name and active_model else ""
    first_ref = providers.resolve_first_model_ref()
    candidates = [
        ref for ref in (active_ref, first_ref) if ref and providers.is_model_ref_usable(ref)
    ]
    if candidates:
        return min(candidates, key=_generator_model_score)

    return None


def _generator_model_score(model_ref: str) -> tuple[int, int]:
    """Prefer lower-latency models for best-effort metadata generation."""
    _provider, _sep, model = model_ref.lower().partition("/")
    if any(hint in model for hint in _GENERATOR_LIGHTWEIGHT_MODEL_HINTS):
        return (0, len(model_ref))
    return (1, len(model_ref))


async def _try_generate_skillhub_manifest_assets(
    *,
    server: Any,
    item: Any,
    requested_model: str | None,
) -> bool:
    """Best-effort model enrichment for cached SkillHub expert manifest."""
    assert server.app_runtime is not None
    registry = server.app_runtime.agent_registry
    harness_manager = registry.harness_manager
    factory = harness_manager.shared_factory if harness_manager is not None else None
    if factory is None:
        logger.info("skip SkillHub manifest generation for %s: no model factory", item.slug)
        return False

    model_ref = _resolve_generator_model_ref(server, requested_model)
    if not model_ref:
        logger.info("skip SkillHub manifest generation for %s: no usable model", item.slug)
        return False
    try:
        llm = factory.get(model_ref)
    except Exception as exc:
        logger.warning(
            "skip SkillHub manifest generation for %s: model %s unavailable: %s",
            item.slug,
            model_ref,
            exc,
        )
        return False

    expert_dir = server.paths.expert_market_dir / item.expert_id
    try:
        return await generate_and_apply_skillhub_manifest_assets(
            llm=llm,
            item=item,
            expert_dir=expert_dir,
            model_ref=model_ref,
            timeout=_SKILLHUB_MANIFEST_GENERATION_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "SkillHub manifest generation failed slug=%s model=%s type=%s error=%r",
            item.slug,
            model_ref,
            exc.__class__.__name__,
            exc,
        )
        return False


async def create_agent_from_skillhub_skillset(
    *,
    server: Any,
    user: Any,
    slug: str,
    options: SkillHubMarketAgentCreateOptions,
) -> SkillHubMarketAgentCreateResult:
    """Install a SkillHub skillset template and create an Octop agent from it."""
    catalog = server.expert_catalog
    if catalog is None:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            "expert catalog is not available",
            status=503,
        )
    assert server.app_runtime is not None

    item = await asyncio.to_thread(
        install_skillset_template,
        slug=slug,
        cache_root=server.paths.expert_market_dir,
    )

    quick_prompts_generated = await _try_generate_skillhub_manifest_assets(
        server=server,
        item=item,
        requested_model=options.default_model,
    )
    catalog.refresh()
    expert = catalog.get(item.expert_id)
    if expert is None:
        raise SkillHubMarketError(f"SkillHub expert template {item.expert_id!r} was not cached")

    config_extra: dict[str, Any] = {
        "expert_source": {
            "type": "skillhub",
            "kind": "skillset",
            "slug": item.slug,
        }
    }
    if options.providers:
        config_extra["providers"] = list(options.providers)
    if options.backend:
        config_extra["backend"] = options.backend

    locale = resolve_user_locale(
        user_repo=server.services.user_repo,
        user_id=user.id,
    )
    spec = build_create_spec_from_expert(
        expert_id=item.expert_id,
        expert=expert,
        user_id=user.id,
        name=options.name,
        description=options.description,
        locale=locale,
        default_model=options.default_model,
        config_extra=config_extra,
    )
    row = await server.app_runtime.agent_registry.create(spec, defer_bootstrap=True)
    return SkillHubMarketAgentCreateResult(
        row=row,
        expert_id=item.expert_id,
        icon_name=expert.summary.icon_name,
        color=expert.summary.color,
        slug=item.slug,
        quick_prompts_generated=quick_prompts_generated,
    )
