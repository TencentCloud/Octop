"""Global default memory extraction settings (Admin → Memory)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from octop.api.common.memory_model import validate_memory_model_ref
from octop.api.deps import get_server, require_permission
from octop.infra.agents.manager import memory_extract_supported_options
from octop.infra.agents.settings.memory_defaults import (
    MAX_EXTRACT_RULE_CHARS,
    GlobalMemoryDefaults,
    normalize_rule_text,
)

router = APIRouter()


class GlobalMemoryDefaultsBody(BaseModel):
    """Patch body for ``PUT /api/settings/memory-defaults``."""

    aux_model: str | None = Field(
        default=None,
        description=(
            "Global default 'provider/model' ref for memory extraction. "
            "Pass '' or null to clear (inherit experts follow their own chat model)."
        ),
    )
    extract_keep_rules: str | None = Field(
        default=None,
        description=(
            "Guidance describing information worth retaining as long-term memory "
            f"(at most {MAX_EXTRACT_RULE_CHARS} chars; '' clears)."
        ),
    )
    extract_skip_rules: str | None = Field(
        default=None,
        description=(
            "Guidance describing information that should be skipped during memory extraction "
            f"(at most {MAX_EXTRACT_RULE_CHARS} chars; '' clears)."
        ),
    )


def _validate_rule_field(name: str, value: Any) -> str:
    try:
        return normalize_rule_text(value, strict=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{name}: {exc}") from exc


def _render_view(
    defaults: GlobalMemoryDefaults,
    *,
    providers: Any,
    affected_agent_count: int | None = None,
) -> dict[str, Any]:
    usable = bool(defaults.aux_model and providers.is_model_ref_usable(defaults.aux_model))
    out: dict[str, Any] = {
        "aux_model": defaults.aux_model,
        "aux_model_usable": usable if defaults.aux_model else True,
        "extract_keep_rules": defaults.extract_keep_rules,
        "extract_skip_rules": defaults.extract_skip_rules,
        "supported_call_options": memory_extract_supported_options(),
    }
    if affected_agent_count is not None:
        out["affected_agent_count"] = affected_agent_count
    return out


@router.get("/settings/memory-defaults", summary="Get global default memory extraction settings")
async def get_global_memory_defaults(
    _: Any = Depends(require_permission("memory_defaults")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return process-wide default extraction model and retention/skip rules."""
    registry = server.app_runtime.agent_registry
    defaults = registry.get_global_memory_defaults()
    return _render_view(defaults, providers=registry.providers)


@router.put(
    "/settings/memory-defaults",
    summary="Update global default memory extraction settings",
)
async def put_global_memory_defaults(
    body: GlobalMemoryDefaultsBody = Body(default_factory=GlobalMemoryDefaultsBody),
    user: Any = Depends(require_permission("memory_defaults")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Persist global default extraction settings and hot-reload inheriting experts."""
    registry = server.app_runtime.agent_registry
    current = registry.get_global_memory_defaults()
    fields_set = body.model_fields_set

    aux_model = (
        validate_memory_model_ref(body.aux_model, registry, user.id)
        if "aux_model" in fields_set
        else current.aux_model
    )
    keep_rules = (
        _validate_rule_field("extract_keep_rules", body.extract_keep_rules)
        if "extract_keep_rules" in fields_set
        else current.extract_keep_rules
    )
    skip_rules = (
        _validate_rule_field("extract_skip_rules", body.extract_skip_rules)
        if "extract_skip_rules" in fields_set
        else current.extract_skip_rules
    )

    saved, affected_ids = await registry.save_global_memory_defaults(
        GlobalMemoryDefaults(
            aux_model=aux_model,
            extract_keep_rules=keep_rules,
            extract_skip_rules=skip_rules,
        )
    )
    return _render_view(
        saved,
        providers=registry.providers,
        affected_agent_count=len(affected_ids),
    )


__all__ = ["router"]
