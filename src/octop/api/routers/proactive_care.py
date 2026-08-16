"""Proactive care push configuration API.

Exposes GET/PUT /api/agents/{agent_id}/proactive-care endpoints for reading and
updating an agent's proactive care push configuration.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator, model_validator

from octop.api.common.agent import require_agent_owner_row
from octop.api.deps import current_user, get_server
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
        """Validate the active hours: start must be earlier than end."""
        from octop.infra.proactive.scheduler import _parse_hhmm  # noqa: PLC0415

        start_t = _parse_hhmm(self.active_hours_start)
        end_t = _parse_hhmm(self.active_hours_end)
        if start_t >= end_t:
            raise ValueError(
                f"active_hours_start ({self.active_hours_start}) 必须早于 "
                f"active_hours_end ({self.active_hours_end})"
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


def _config_to_dict(cfg: ProactiveCareConfig) -> dict[str, Any]:
    return {
        "enabled": cfg.enabled,
        "active_hours_start": cfg.active_hours_start,
        "active_hours_end": cfg.active_hours_end,
        "min_interval_hours": cfg.min_interval_hours,
        "max_interval_hours": cfg.max_interval_hours,
    }


def _get_proactive_scheduler(server: Any) -> Any:
    assert server.app_runtime is not None
    return server.app_runtime.proactive_scheduler


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
    require_agent_owner_row(agent_id, user=user, as_user=None, server=server)
    cfg = server.services.repos.proactive_care_config_repo.get(agent_id)
    return _config_to_dict(cfg)


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
    - active_hours_start < active_hours_end
    - min_interval_hours <= max_interval_hours
    - min_interval_hours >= 1
    """
    require_agent_owner_row(agent_id, user=user, as_user=None, server=server)

    cfg = ProactiveCareConfig(
        agent_id=agent_id,
        enabled=body.enabled,
        active_hours_start=body.active_hours_start,
        active_hours_end=body.active_hours_end,
        min_interval_hours=body.min_interval_hours,
        max_interval_hours=body.max_interval_hours,
    )
    server.services.repos.proactive_care_config_repo.upsert(cfg)

    # Immediately update the scheduler task
    scheduler = _get_proactive_scheduler(server)
    scheduler.reschedule(agent_id)

    return _config_to_dict(cfg)
