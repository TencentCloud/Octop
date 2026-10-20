"""Apply LLM generation settings from ``RunnableConfig.configurable``.

Hosts (e.g. Octop) map agent config onto these configurable keys before
``stream`` / ``invoke``. This middleware merges them into each model call.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from octop_harness.middleware.runtime import runtime_config

CONFIGURABLE_MODEL_SETTINGS = "model_settings"
CONFIGURABLE_MAX_INPUT_TOKENS = "max_input_tokens"


def apply_configurable_model_settings(request: ModelRequest) -> ModelRequest:
    """Merge host overrides into ``request.model_settings`` and context cap."""
    cfg = runtime_config(request)
    configurable = cfg.get("configurable") if isinstance(cfg, dict) else None
    if not isinstance(configurable, dict):
        return request

    updated = request
    overrides = configurable.get(CONFIGURABLE_MODEL_SETTINGS)
    if isinstance(overrides, dict) and overrides:
        merged = dict(getattr(request, "model_settings", None) or {})
        merged.update(overrides)
        updated = updated.override(model_settings=merged)

    max_input = configurable.get(CONFIGURABLE_MAX_INPUT_TOKENS)
    model = getattr(updated, "model", None)
    if model is not None:
        profile = getattr(model, "profile", None)
        if not isinstance(profile, dict):
            profile = {}
            try:
                object.__setattr__(model, "profile", profile)
            except (AttributeError, TypeError):
                return updated

        if isinstance(max_input, int) and max_input > 0:
            # A host-level prompt cap is explicit and takes precedence.
            profile["max_input_tokens"] = max_input
        else:
            base_input = getattr(model, "_harness_max_input_tokens", 0)
            context_window = getattr(model, "_harness_context_window", 0)
            if not isinstance(base_input, int) or base_input <= 0:
                raw_base = profile.get("max_input_tokens")
                base_input = raw_base if isinstance(raw_base, int) else 0
            if not isinstance(context_window, int) or context_window <= 0:
                raw_context = profile.get("context_window")
                context_window = raw_context if isinstance(raw_context, int) else 0

            output_tokens = (getattr(updated, "model_settings", None) or {}).get("max_tokens")
            if isinstance(output_tokens, int) and output_tokens > 0 and context_window > 0:
                safe_input = max(context_window - output_tokens, 1)
                profile["max_input_tokens"] = min(base_input, safe_input) if base_input > 0 else safe_input
            elif base_input > 0:
                # Restore the baseline after a previous request reserved output.
                profile["max_input_tokens"] = base_input
    return updated


class ModelSettingsMiddleware(AgentMiddleware[Any, Any]):
    """Inject ``temperature`` / ``top_p`` / ``max_tokens`` from configurable."""

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(apply_configurable_model_settings(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(apply_configurable_model_settings(request))


__all__ = [
    "CONFIGURABLE_MAX_INPUT_TOKENS",
    "CONFIGURABLE_MODEL_SETTINGS",
    "ModelSettingsMiddleware",
    "apply_configurable_model_settings",
]
