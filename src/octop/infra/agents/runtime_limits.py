"""Map agent ``config_json`` runtime knobs onto harness-agent semantics.

Configurable stream contract (``ChatRequest.configurable``)
-----------------------------------------------------------
``max_iters``              → top-level ``recursion_limit`` (LangGraph)
``temperature``/``top_p``/``max_tokens`` → ``CONFIGURABLE_MODEL_SETTINGS``
                                           → harness ``ModelSettingsMiddleware``
                                           → ``model.bind(...)`` (LLM body)
``max_input_length``       → ``CONFIGURABLE_MAX_INPUT_TOKENS``
                                           → ``model.profile["max_input_tokens"]``
"""

from __future__ import annotations

from typing import Any

from harness_agent.middleware.model_settings import (
    CONFIGURABLE_MAX_INPUT_TOKENS,
    CONFIGURABLE_MODEL_SETTINGS,
)

AGENT_RUNTIME_CONFIG_KEYS = (
    "max_iters",
    "max_input_length",
    "temperature",
    "top_p",
    "max_tokens",
)

_DEFAULT_MAX_INPUT_TOKENS = 128_000


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value.is_integer():
        iv = int(value)
        return iv if iv > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        iv = int(value.strip())
        return iv if iv > 0 else None
    return None


def agent_recursion_limit(cfg: dict[str, Any]) -> int | None:
    """Return LangGraph ``recursion_limit`` from ``max_iters`` when configured."""
    return _positive_int(cfg.get("max_iters"))


def agent_max_input_tokens(cfg: dict[str, Any]) -> int | None:
    """Return context-window cap override from ``max_input_length`` when configured."""
    return _positive_int(cfg.get("max_input_length"))


def _unit_float(value: Any, *, min_val: float, max_val: float) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
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
    "agent_max_input_tokens",
    "agent_model_settings",
    "agent_recursion_limit",
    "agent_runtime_values",
    "apply_agent_runtime_to_stream_request",
    "merge_agent_runtime_values",
    "resolve_context_max_tokens",
]
