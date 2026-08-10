"""Typed API fields for per-agent runtime and model settings."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from octop.infra.agents.runtime_limits import AGENT_RUNTIME_CONFIG_KEYS


class AgentRuntimeFields(BaseModel):
    """First-class create/edit fields persisted in the agent's config storage."""

    max_iters: int | None = Field(default=None, ge=1)
    max_input_length: int | None = Field(default=None, ge=1_000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1)


def runtime_field_updates(
    model: BaseModel,
    *,
    exclude_unset: bool,
) -> dict[str, Any]:
    """Extract runtime fields from an API body without leaking unrelated fields."""
    dumped = model.model_dump(exclude_unset=exclude_unset)
    return {key: dumped[key] for key in AGENT_RUNTIME_CONFIG_KEYS if key in dumped}


__all__ = ["AgentRuntimeFields", "runtime_field_updates"]
