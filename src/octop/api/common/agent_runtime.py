"""Typed API fields for per-agent runtime and model settings."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from octop.infra.agents.settings.compaction import (
    COMPACTION_CONFIG_KEY,
    DEFAULT_TRIGGER_FRACTION,
    MIN_TRIM_TOKENS,
)
from octop.infra.agents.settings.runtime_limits import (
    AGENT_RUNTIME_CONFIG_KEYS,
    DEFAULT_RETRY_INITIAL_DELAY,
    DEFAULT_RETRY_MAX_DELAY,
)


class AgentCompactionSettings(BaseModel):
    """Automatic context compaction for one expert. Omitted fields keep the harness default."""

    model: str | None = Field(
        default=None,
        description="Manual /compact model: provider/model, session, or null to inherit.",
    )
    enabled: bool | None = Field(
        default=None,
        description="Turn automatic compaction off. Omit to leave it on.",
    )
    trigger_fraction: float | None = Field(
        default=None,
        gt=0,
        le=1,
        description="Fraction of the context window that starts compaction. Default 0.85.",
    )
    keep_fraction: float | None = Field(
        default=None,
        gt=0,
        lt=1,
        description="Fraction of the context window kept after compaction. Default 0.10.",
    )
    trim_tokens: int | None = Field(
        default=None,
        ge=MIN_TRIM_TOKENS,
        description="Max tokens of evicted history sent to the summary model. Default 8000.",
    )

    @model_validator(mode="after")
    def keep_below_trigger(self) -> AgentCompactionSettings:
        if self.keep_fraction is None:
            return self
        trigger = (
            self.trigger_fraction if self.trigger_fraction is not None else DEFAULT_TRIGGER_FRACTION
        )
        if self.keep_fraction >= trigger:
            raise ValueError("keep_fraction must be less than trigger_fraction")
        return self


class AgentRuntimeFields(BaseModel):
    """First-class create/edit fields persisted in the agent's config storage."""

    max_iters: int | None = Field(default=None, ge=1)
    max_input_length: int | None = Field(default=None, ge=1_000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1)
    tool_call_limit_enabled: bool | None = Field(
        default=None,
        description=(
            "Stop a turn that repeats one tool call with the same arguments. "
            "Omit to leave the limit on."
        ),
    )
    tool_call_run_limit: int | None = Field(
        default=None,
        ge=1,
        description=(
            "How many times the same tool may be called in a row with the same "
            "arguments. Omit to use 40."
        ),
    )
    model_retry_enabled: bool | None = Field(
        default=None,
        description="Retry a model call that raises. Omit to leave retries on.",
    )
    model_retry_max_retries: int | None = Field(
        default=None,
        ge=0,
        description="Retries after the first model call. Omit to use 2.",
    )
    model_retry_initial_delay: float | None = Field(
        default=None,
        gt=0,
        description="Seconds before the first model retry. Omit to use 1.",
    )
    model_retry_max_delay: float | None = Field(
        default=None,
        gt=0,
        description="Maximum seconds between model retries. Omit to use 60.",
    )
    tool_retry_enabled: bool | None = Field(
        default=None,
        description="Retry a tool call that raises. Omit to leave retries on.",
    )
    tool_retry_max_retries: int | None = Field(
        default=None,
        ge=0,
        description="Retries after the first tool call. Omit to use 5.",
    )
    tool_retry_initial_delay: float | None = Field(
        default=None,
        gt=0,
        description="Seconds before the first tool retry. Omit to use 1.",
    )
    tool_retry_max_delay: float | None = Field(
        default=None,
        gt=0,
        description="Maximum seconds between tool retries. Omit to use 60.",
    )
    compaction: AgentCompactionSettings | None = None

    @model_validator(mode="after")
    def retry_delay_window(self) -> AgentRuntimeFields:
        for prefix in ("model_retry", "tool_retry"):
            initial = getattr(self, f"{prefix}_initial_delay")
            maximum = getattr(self, f"{prefix}_max_delay")
            initial_value = DEFAULT_RETRY_INITIAL_DELAY if initial is None else initial
            maximum_value = DEFAULT_RETRY_MAX_DELAY if maximum is None else maximum
            if maximum_value < initial_value:
                raise ValueError(
                    f"{prefix}_max_delay must be greater than or equal to {prefix}_initial_delay"
                )
        return self


def validate_compaction_override(model: Any, registry: Any, user_id: int) -> None:
    settings = model.compaction
    if settings is not None and settings.model not in (None, "session"):
        registry.validate_compaction_model(user_id, settings.model)


def persisted_agent_settings(
    model: BaseModel,
    *,
    exclude_unset: bool,
    registry: Any,
    user_id: int,
) -> dict[str, Any]:
    """Runtime fields plus compaction for create paths that share one dict."""
    validate_compaction_override(model, registry, user_id)
    dumped = model.model_dump(exclude_unset=exclude_unset)
    updates = {key: dumped[key] for key in AGENT_RUNTIME_CONFIG_KEYS if key in dumped}
    if COMPACTION_CONFIG_KEY in dumped:
        updates[COMPACTION_CONFIG_KEY] = dumped[COMPACTION_CONFIG_KEY]
    return updates


__all__ = [
    "AgentCompactionSettings",
    "AgentRuntimeFields",
    "persisted_agent_settings",
]
