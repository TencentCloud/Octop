"""Create agents from SkillHub-backed expert market templates."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

from octop.infra.agents.experts.catalog import MANIFEST_FILENAME, build_create_spec_from_expert
from octop.infra.agents.experts.manifest_generator import (
    build_skillhub_agent_manifest_bytes,
)
from octop.infra.agents.experts.skillhub_market import (
    SkillHubMarketError,
    SkillHubMarketErrorKind,
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

WelcomeEnrichment = Literal["pending", "skipped", "succeeded", "failed"]


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
    welcome_enrichment: WelcomeEnrichment


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


def _resolve_generator_llm(
    *,
    server: Any,
    requested_model: str | None,
    slug: str,
) -> tuple[Any, str] | None:
    """Return ``(llm, model_ref)`` or ``None`` when generation should be skipped."""
    assert server.app_runtime is not None
    registry = server.app_runtime.agent_registry
    harness_manager = registry.harness_manager
    factory = harness_manager.shared_factory if harness_manager is not None else None
    if factory is None:
        logger.info("skip SkillHub manifest generation for %s: no model factory", slug)
        return None

    model_ref = _resolve_generator_model_ref(server, requested_model)
    if not model_ref:
        logger.info("skip SkillHub manifest generation for %s: no usable model", slug)
        return None
    try:
        return factory.get(model_ref), model_ref
    except Exception as exc:
        logger.warning(
            "skip SkillHub manifest generation for %s: model %s unavailable: %s",
            slug,
            model_ref,
            exc,
        )
        return None


def _set_welcome_enrichment_status(
    *,
    server: Any,
    agent_id: str,
    status: WelcomeEnrichment,
) -> None:
    """Persist enrichment status on agent config without forcing a harness reload."""
    registry = server.app_runtime.agent_registry
    assert registry is not None
    cfg = dict(registry.get_config(agent_id))
    source = cfg.get("expert_source")
    if isinstance(source, dict):
        cfg["expert_source"] = {**source, "welcome_enrichment": status}
    else:
        cfg["welcome_enrichment"] = status
    server.services.agent_repo.update_config(
        agent_id,
        config_json=json.dumps(cfg, ensure_ascii=False),
    )


async def _enrich_agent_welcome_async(
    *,
    server: Any,
    item: Any,
    agent_id: str,
    requested_model: str | None,
) -> None:
    """Background: LLM-enrich welcome cards and write only the agent workspace copy.

    The shared SkillHub cache under ``expert_market/`` stays deterministic so
    concurrent installs of the same slug cannot clobber each other.
    """
    try:
        resolved = _resolve_generator_llm(
            server=server,
            requested_model=requested_model,
            slug=item.slug,
        )
        if resolved is None:
            _set_welcome_enrichment_status(
                server=server,
                agent_id=agent_id,
                status="skipped",
            )
            return
        llm, model_ref = resolved
        expert_dir = server.paths.expert_market_dir / item.expert_id
        payload = await build_skillhub_agent_manifest_bytes(
            llm=llm,
            item=item,
            expert_dir=expert_dir,
            model_ref=model_ref,
            timeout=_SKILLHUB_MANIFEST_GENERATION_TIMEOUT_SECONDS,
        )
        assert server.app_runtime is not None
        registry = server.app_runtime.agent_registry
        workspace = registry.workspace_for_agent(agent_id)
        if workspace is None:
            logger.info(
                "SkillHub welcome enrichment skipped upload agent=%s: no workspace",
                agent_id,
            )
            _set_welcome_enrichment_status(
                server=server,
                agent_id=agent_id,
                status="failed",
            )
            return
        await workspace.aupload_many([(MANIFEST_FILENAME, payload)])
        _set_welcome_enrichment_status(
            server=server,
            agent_id=agent_id,
            status="succeeded",
        )
        logger.info(
            "SkillHub welcome enrichment applied agent=%s slug=%s",
            agent_id,
            item.slug,
        )
    except Exception:
        logger.warning(
            "SkillHub welcome enrichment failed agent=%s slug=%s",
            agent_id,
            item.slug,
            exc_info=True,
        )
        try:
            _set_welcome_enrichment_status(
                server=server,
                agent_id=agent_id,
                status="failed",
            )
        except Exception:
            logger.warning(
                "failed to persist welcome enrichment failure agent=%s",
                agent_id,
                exc_info=True,
            )


async def create_agent_from_skillhub_skillset(
    *,
    server: Any,
    user: Any,
    slug: str,
    options: SkillHubMarketAgentCreateOptions,
) -> SkillHubMarketAgentCreateResult:
    """Install a SkillHub skillset template and create an Octop agent from it.

    Welcome / quick-prompt cards use the deterministic SkillHub workflow first so
    create stays fast. Optional LLM enrichment runs in the background and updates
    only this agent's workspace ``manifest.json`` when ready.
    """
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

    catalog.refresh()
    expert = catalog.get(item.expert_id)
    if expert is None:
        raise SkillHubMarketError(
            f"SkillHub expert template {item.expert_id!r} was not cached",
            kind=SkillHubMarketErrorKind.PACKAGE_INVALID,
        )

    can_enrich = (
        _resolve_generator_llm(
            server=server,
            requested_model=options.default_model,
            slug=item.slug,
        )
        is not None
    )
    welcome_enrichment: WelcomeEnrichment = "pending" if can_enrich else "skipped"

    config_extra: dict[str, Any] = {
        "expert_source": {
            "type": "skillhub",
            "kind": "skillset",
            "slug": item.slug,
            "welcome_enrichment": welcome_enrichment,
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

    if can_enrich:
        asyncio.create_task(
            _enrich_agent_welcome_async(
                server=server,
                item=item,
                agent_id=row.agent_id,
                requested_model=options.default_model,
            ),
            name=f"skillhub-welcome-{row.agent_id}",
        )

    return SkillHubMarketAgentCreateResult(
        row=row,
        expert_id=item.expert_id,
        icon_name=expert.summary.icon_name,
        color=expert.summary.color,
        slug=item.slug,
        welcome_enrichment=welcome_enrichment,
    )
