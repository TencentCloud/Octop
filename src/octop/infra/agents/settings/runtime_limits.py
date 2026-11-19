"""Map agent ``config_json`` runtime knobs onto octop-harness semantics.

Configurable stream contract (``ChatRequest.configurable``)
-----------------------------------------------------------
``max_iters``              → top-level ``recursion_limit`` (LangGraph)
``temperature``/``top_p``/``max_tokens`` → ``CONFIGURABLE_MODEL_SETTINGS``
                                           → harness ``ModelSettingsMiddleware``
                                           → ``model.bind(...)`` (LLM body)
``max_input_length``       → ``CONFIGURABLE_MAX_INPUT_TOKENS``
                                           → ``model.profile["max_input_tokens"]``

Start-time middleware (read in ``AgentManager._build_harness_config``)
-----------------------------------------------------------------------
``tool_call_limit_enabled`` / ``tool_call_run_limit``
    → ``ConsecutiveToolCallMiddleware`` (identical calls in a row; default 40)
``model_retry_*`` → the host model-retry middleware (default on, 2 retries)
``tool_retry_*``  → LangChain ``ToolRetryMiddleware`` (default on, 5 retries)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from octop_harness.middleware.model_settings import (
    CONFIGURABLE_MAX_INPUT_TOKENS,
    CONFIGURABLE_MODEL_SETTINGS,
)

AGENT_RUNTIME_CONFIG_KEYS = (
    "max_iters",
    "max_input_length",
    "temperature",
    "top_p",
    "max_tokens",
    "tool_call_limit_enabled",
    "tool_call_run_limit",
    "model_retry_enabled",
    "model_retry_max_retries",
    "model_retry_initial_delay",
    "model_retry_max_delay",
    "tool_retry_enabled",
    "tool_retry_max_retries",
    "tool_retry_initial_delay",
    "tool_retry_max_delay",
)

_DEFAULT_MAX_INPUT_TOKENS = 128_000
DEFAULT_TOOL_CALL_RUN_LIMIT = 40
DEFAULT_MODEL_RETRY_MAX_RETRIES = 2
DEFAULT_TOOL_RETRY_MAX_RETRIES = 5
DEFAULT_RETRY_INITIAL_DELAY = 1.0
DEFAULT_RETRY_MAX_DELAY = 60.0


def _int_at_least(value: Any, minimum: int) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float) and value.is_integer():
        parsed = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        return None
    return parsed if parsed >= minimum else None


def _positive_int(value: Any) -> int | None:
    return _int_at_least(value, 1)


def _non_negative_int(value: Any) -> int | None:
    return _int_at_least(value, 0)


def _positive_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = float(stripped)
        except ValueError:
            return None
    else:
        parsed = float(value)
    return parsed if parsed > 0 else None


def _stored_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


@dataclass(frozen=True)
class RetryBudget:
    """Resolved model or tool retry settings for one expert."""

    enabled: bool
    max_retries: int
    initial_delay: float
    max_delay: float


def _retry_budget(
    cfg: dict[str, Any],
    *,
    enabled_key: str,
    retries_key: str,
    initial_key: str,
    max_key: str,
    default_retries: int,
) -> RetryBudget:
    initial = _positive_float(cfg.get(initial_key))
    maximum = _positive_float(cfg.get(max_key))
    retries = _non_negative_int(cfg.get(retries_key))
    initial_delay = initial if initial is not None else DEFAULT_RETRY_INITIAL_DELAY
    max_delay = maximum if maximum is not None else DEFAULT_RETRY_MAX_DELAY
    if max_delay < initial_delay:
        max_delay = initial_delay
    return RetryBudget(
        enabled=_stored_bool(cfg.get(enabled_key), default=True),
        max_retries=retries if retries is not None else default_retries,
        initial_delay=initial_delay,
        max_delay=max_delay,
    )


def resolve_model_retry(cfg: dict[str, Any]) -> RetryBudget:
    """Model-call retry budget. Missing keys keep the host default (on, 2)."""
    return _retry_budget(
        cfg,
        enabled_key="model_retry_enabled",
        retries_key="model_retry_max_retries",
        initial_key="model_retry_initial_delay",
        max_key="model_retry_max_delay",
        default_retries=DEFAULT_MODEL_RETRY_MAX_RETRIES,
    )


def resolve_tool_retry(cfg: dict[str, Any]) -> RetryBudget:
    """Tool-exception retry budget. Missing keys keep the default (on, 5)."""
    return _retry_budget(
        cfg,
        enabled_key="tool_retry_enabled",
        retries_key="tool_retry_max_retries",
        initial_key="tool_retry_initial_delay",
        max_key="tool_retry_max_delay",
        default_retries=DEFAULT_TOOL_RETRY_MAX_RETRIES,
    )


def resolve_tool_call_run_limit(cfg: dict[str, Any]) -> int | None:
    """Cap on identical tool calls in a row. ``None`` means it is not mounted.

    Different tools and different arguments do not add up. An absent switch
    stays on. An absent count uses :data:`DEFAULT_TOOL_CALL_RUN_LIMIT`.
    """
    if not _stored_bool(cfg.get("tool_call_limit_enabled"), default=True):
        return None
    limit = _positive_int(cfg.get("tool_call_run_limit"))
    return limit if limit is not None else DEFAULT_TOOL_CALL_RUN_LIMIT


def call_guard_middleware(cfg: dict[str, Any]) -> list[Any]:
    """Consecutive identical-call cap and tool-exception retry for one expert."""
    from langchain.agents.middleware import ToolRetryMiddleware

    from octop.infra.agents.middleware.consecutive_tool_call import (
        ConsecutiveToolCallMiddleware,
    )

    middleware: list[Any] = []
    run_limit = resolve_tool_call_run_limit(cfg)
    if run_limit is not None:
        middleware.append(ConsecutiveToolCallMiddleware(limit=run_limit))
    tool_retry = resolve_tool_retry(cfg)
    if tool_retry.enabled:
        middleware.append(
            ToolRetryMiddleware(
                max_retries=tool_retry.max_retries,
                initial_delay=tool_retry.initial_delay,
                max_delay=tool_retry.max_delay,
                on_failure="continue",
            )
        )
    return middleware


def agent_recursion_limit(cfg: dict[str, Any]) -> int | None:
    """Return LangGraph ``recursion_limit`` from ``max_iters`` when configured."""
    return _positive_int(cfg.get("max_iters"))


def agent_max_input_tokens(cfg: dict[str, Any]) -> int | None:
    """Return context-window cap override from ``max_input_length`` when configured."""
    return _positive_int(cfg.get("max_input_length"))


def _unit_float(value: Any, *, min_val: float, max_val: float) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        parsed = float(value)
        return parsed if min_val <= parsed <= max_val else None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = float(stripped)
        except ValueError:
            return None
        return parsed if min_val <= parsed <= max_val else None
    return None


def _agent_temperature(cfg: dict[str, Any]) -> float | None:
    """Return sampling temperature from agent config when configured."""
    return _unit_float(cfg.get("temperature"), min_val=0.0, max_val=2.0)


def _agent_top_p(cfg: dict[str, Any]) -> float | None:
    """Return nucleus sampling ``top_p`` from agent config when configured."""
    return _unit_float(cfg.get("top_p"), min_val=0.0, max_val=1.0)


def _agent_max_output_tokens(cfg: dict[str, Any]) -> int | None:
    """Return max output tokens from agent ``max_tokens`` when configured."""
    return _positive_int(cfg.get("max_tokens"))


def agent_model_settings(cfg: dict[str, Any]) -> dict[str, Any]:
    """Map agent config onto LangChain ``model.bind(...)`` kwargs."""
    settings: dict[str, Any] = {}
    temperature = _agent_temperature(cfg)
    if temperature is not None:
        settings["temperature"] = temperature
    top_p = _agent_top_p(cfg)
    if top_p is not None:
        settings["top_p"] = top_p
    max_tokens = _agent_max_output_tokens(cfg)
    if max_tokens is not None:
        settings["max_tokens"] = max_tokens
    return settings


def resolve_context_max_tokens(
    cfg: dict[str, Any], *, fallback: int = _DEFAULT_MAX_INPUT_TOKENS
) -> int:
    """Resolve the token cap used for context usage UI and breakdown."""
    override = agent_max_input_tokens(cfg)
    return override if override is not None else fallback


def agent_runtime_values(cfg: dict[str, Any]) -> dict[str, Any]:
    """Return first-class agent runtime fields from the persisted config."""
    return {key: cfg.get(key) for key in AGENT_RUNTIME_CONFIG_KEYS}


def merge_agent_runtime_values(
    cfg: dict[str, Any],
    values: dict[str, Any],
) -> dict[str, Any]:
    """Persist first-class runtime fields inside one agent's config storage."""
    merged = dict(cfg)
    for key in AGENT_RUNTIME_CONFIG_KEYS:
        if key not in values:
            continue
        value = values[key]
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def apply_agent_runtime_to_stream_request(
    req: dict[str, Any],
    agent_cfg: dict[str, Any],
) -> dict[str, Any]:
    """Merge agent runtime knobs into a harness ``stream`` request dict."""
    out = dict(req)

    recursion_limit = agent_recursion_limit(agent_cfg)
    if recursion_limit is not None and out.get("recursion_limit") is None:
        out["recursion_limit"] = recursion_limit

    configurable_updates: dict[str, Any] = {}
    model_settings = agent_model_settings(agent_cfg)
    if model_settings:
        existing_cfg = out.get("configurable")
        existing_settings = (
            existing_cfg.get(CONFIGURABLE_MODEL_SETTINGS)
            if isinstance(existing_cfg, dict)
            else None
        )
        merged_settings = dict(existing_settings) if isinstance(existing_settings, dict) else {}
        merged_settings.update(model_settings)
        configurable_updates[CONFIGURABLE_MODEL_SETTINGS] = merged_settings

    max_input_tokens = agent_max_input_tokens(agent_cfg)
    if max_input_tokens is not None:
        configurable_updates[CONFIGURABLE_MAX_INPUT_TOKENS] = max_input_tokens

    if configurable_updates:
        configurable = dict(out.get("configurable") or {})
        configurable.update(configurable_updates)
        out["configurable"] = configurable

    return out


__all__ = [
    "AGENT_RUNTIME_CONFIG_KEYS",
    "CONFIGURABLE_MAX_INPUT_TOKENS",
    "CONFIGURABLE_MODEL_SETTINGS",
    "DEFAULT_MODEL_RETRY_MAX_RETRIES",
    "DEFAULT_RETRY_INITIAL_DELAY",
    "DEFAULT_RETRY_MAX_DELAY",
    "DEFAULT_TOOL_CALL_RUN_LIMIT",
    "DEFAULT_TOOL_RETRY_MAX_RETRIES",
    "RetryBudget",
    "agent_max_input_tokens",
    "agent_model_settings",
    "agent_recursion_limit",
    "agent_runtime_values",
    "apply_agent_runtime_to_stream_request",
    "call_guard_middleware",
    "merge_agent_runtime_values",
    "resolve_context_max_tokens",
    "resolve_model_retry",
    "resolve_tool_call_run_limit",
    "resolve_tool_retry",
]
