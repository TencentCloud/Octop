"""Proactive care push configuration API.

Exposes GET/PUT /api/agents/{agent_id}/proactive-care endpoints for reading and
updating an agent's proactive care push configuration.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from octop.api.common.agent import require_agent_owner_row
from octop.api.common.memory_model import validate_model_ref
from octop.api.deps import current_user, get_server
from octop.infra.agents.providers.reasoning import supports_reasoning_setting
from octop.infra.db.repos.proactive_care_config import ProactiveCareConfig

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ProactiveCareConfigBody(BaseModel):
    """Proactive care push configuration request body."""

    enabled: bool = True
    active_hours_start: str = "09:00"
    active_hours_end: str = "22:00"
    min_interval_hours: int = 5
    max_interval_hours: int = 24
    model_ref: str | None = Field(
        default=None,
        description="Care model in provider/model form; null follows the agent default.",
    )
    reasoning_effort: str = Field(
        default="auto",
        min_length=1,
        max_length=64,
        description="auto, disabled, or an effort advertised by the selected model.",
    )
    generation_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=3600,
        strict=True,
        description="Time allowed for each generation attempt, in seconds.",
    )

    @field_validator("active_hours_start", "active_hours_end")
    @classmethod
    def validate_hhmm(cls, v: str) -> str:
        """Validate the HH:MM format."""
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError(f"时间格式必须为 HH:MM，收到: {v!r}")
        try:
            h, m = int(parts[0]), int(parts[1])
        except ValueError:
            raise ValueError(f"时间格式必须为 HH:MM，收到: {v!r}") from None
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError(f"时间超出范围: {v!r}")
        return v

    @model_validator(mode="after")
    def validate_time_range(self) -> ProactiveCareConfigBody:
        """Reject an empty window. An earlier end means the window crosses midnight."""
        from octop.infra.proactive.scheduler import _parse_hhmm  # noqa: PLC0415

        start_t = _parse_hhmm(self.active_hours_start)
        end_t = _parse_hhmm(self.active_hours_end)
        if start_t == end_t:
            raise ValueError(
                f"active_hours_start ({self.active_hours_start}) 与 "
                f"active_hours_end ({self.active_hours_end}) 不能相同"
            )
        return self

    @model_validator(mode="after")
    def validate_interval(self) -> ProactiveCareConfigBody:
        """Validate the push interval: min <= max and min >= 1."""
        if self.min_interval_hours < 1:
            raise ValueError("min_interval_hours 不能小于 1 小时（防止频繁打扰）")
        if self.min_interval_hours > self.max_interval_hours:
            raise ValueError(
                f"min_interval_hours ({self.min_interval_hours}) 不能大于 "
                f"max_interval_hours ({self.max_interval_hours})"
            )
        return self


def _config_to_dict(cfg: ProactiveCareConfig, default_model_ref: str | None) -> dict[str, Any]:
    return {
        "model_ref": cfg.model_ref,
        "default_model_ref": default_model_ref,
        "reasoning_effort": cfg.reasoning_effort,
        "generation_timeout_seconds": cfg.generation_timeout_seconds,
        "enabled": cfg.enabled,
        "active_hours_start": cfg.active_hours_start,
        "active_hours_end": cfg.active_hours_end,
        "min_interval_hours": cfg.min_interval_hours,
        "max_interval_hours": cfg.max_interval_hours,
    }


def _visible_default_model(registry: Any, row: Any, user_id: int) -> str | None:
    ref = registry.configured_default_model_ref(row)
    return ref if ref and registry.model_ref_allowed_for_user(user_id, ref) else None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/agents/{agent_id}/proactive-care",
    summary="Get proactive care push configuration",
)
async def get_proactive_care_config(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Read the agent's proactive care push configuration, returning defaults if not configured."""
    row = require_agent_owner_row(agent_id, user=user, as_user=None, server=server)
    registry = server.app_runtime.agent_registry
    owner_id = row.user_id if row.user_id is not None else user.id
    default_ref = _visible_default_model(registry, row, owner_id)
    cfg = server.services.repos.proactive_care_config_repo.get(agent_id)
    return _config_to_dict(cfg, default_ref)


@router.put(
    "/agents/{agent_id}/proactive-care",
    summary="Update proactive care push configuration",
)
async def put_proactive_care_config(
    agent_id: str,
    body: ProactiveCareConfigBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Save the agent's proactive care push configuration and immediately update the scheduler.

    Parameter validation:
    - active_hours_start != active_hours_end (an earlier end crosses midnight)
    - min_interval_hours <= max_interval_hours
    - min_interval_hours >= 1
    """
    row = require_agent_owner_row(agent_id, user=user, as_user=None, server=server)
    registry = server.app_runtime.agent_registry
    owner_id = row.user_id if row.user_id is not None else user.id
    default_ref = _visible_default_model(registry, row, owner_id)

    repo = server.services.repos.proactive_care_config_repo
    fields = body.model_fields_set
    previous = repo.get(agent_id)
    model_ref = previous.model_ref
    if "model_ref" in fields and body.model_ref != previous.model_ref:
        model_ref = validate_model_ref(body.model_ref, registry, owner_id, field="model_ref")
    effort = body.reasoning_effort if "reasoning_effort" in fields else previous.reasoning_effort
    if (model_ref, effort) != (previous.model_ref, previous.reasoning_effort) and effort != "auto":
        ref = model_ref or default_ref
        if not supports_reasoning_setting(
            registry.providers.get_model_reasoning_capability(ref) if ref else None, effort
        ):
            raise HTTPException(
                status_code=422, detail="Unsupported reasoning setting for the selected model"
            )

    cfg = ProactiveCareConfig(
        agent_id=agent_id, model_ref=model_ref, **body.model_dump(exclude={"model_ref"})
    )
    repo.upsert(cfg, generation_fields=fields)
    server.app_runtime.proactive_scheduler.reschedule(agent_id)
    return _config_to_dict(repo.get(agent_id), default_ref)
