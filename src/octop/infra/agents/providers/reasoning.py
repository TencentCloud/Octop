"""Normalize model reasoning capabilities and build provider-specific overrides."""

from __future__ import annotations

from typing import Any

REASONING_MODES = frozenset({"auto", "enabled", "disabled"})
REASONING_ADAPTERS = frozenset(
    {
        "status_only",
        "thinking",
        "thinking_nested_effort",
        "openai_reasoning_effort",
        "anthropic_adaptive",
        "anthropic_budget",
        "dashscope",
        "openrouter",
    }
)
EFFORT_TYPES = frozenset({"enum", "token_budget"})
TOKEN_PLAN_REASONING_MODELS = frozenset(
    {
        "tc-code-latest",
        "minimax-m2.5",
        "minimax-m2.7",
        "glm-5",
        "glm-5.1",
        "kimi-k2.5",
        "deepseek-v4-flash-202605",
        "deepseek-v4-pro-202606",
    }
)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip().lower() for item in value if str(item).strip()]


def _legacy_adapter(model_id: str, *, base_url: str | None) -> str:
    """Choose a conservative adapter for legacy ``reasoning: true`` metadata."""
    url = (base_url or "").lower()
    if "openrouter.ai" in url:
        return "openrouter"
    if "dashscope" in url or "maas.aliyuncs.com" in url:
        return "dashscope"
    if model_id.startswith("deepseek-v4-") and any(
        host in url for host in ("lkeap.cloud.tencent.com", "tencentmaas.com")
    ):
        return "thinking_nested_effort"
    if any(host in url for host in ("deepseek.com", "bigmodel.cn", "z.ai", "moonshot")):
        return "thinking"
    if any(host in url for host in ("openai.com", "generativelanguage.googleapis.com", "groq.com")):
        return "openai_reasoning_effort"
    # Existing Octop metadata historically meant an OpenAI-compatible model
    # with a ``thinking`` object. Keep that behaviour for unknown gateways.
    return "thinking"


def reasoning_capability(
    model: dict[str, Any],
    *,
    base_url: str | None = None,
) -> dict[str, Any] | None:
    """Return a stable capability shape, accepting legacy model metadata."""
    raw = model.get("reasoning_config")
    legacy = model.get("reasoning") is True
    options = model.get("options")
    thinking_option = options.get("thinking") if isinstance(options, dict) else None
    model_id = str(model.get("id") or "").strip().lower()
    known_token_plan_model = model_id in TOKEN_PLAN_REASONING_MODELS
    if not isinstance(raw, dict):
        if not legacy and not isinstance(thinking_option, dict) and not known_token_plan_model:
            return None
        raw = {
            "default_mode": thinking_option.get("type", "enabled")
            if isinstance(thinking_option, dict)
            else "enabled"
            if known_token_plan_model
            else "auto",
            "adapter": _legacy_adapter(model_id, base_url=base_url),
        }
        if model_id in {"minimax-m2.5", "minimax-m2.7"}:
            raw.update(
                {
                    "toggle": False,
                    "default_mode": "enabled",
                    "adapter": "status_only",
                }
            )
        if model_id.startswith("deepseek-v4-"):
            raw.update(
                {
                    "efforts": ["high", "max"],
                    "adapter": "thinking_nested_effort"
                    if any(
                        host in (base_url or "").lower()
                        for host in ("lkeap.cloud.tencent.com", "tencentmaas.com")
                    )
                    else "thinking",
                }
            )

    if raw.get("supported", True) is not True:
        return None
    mode = str(raw.get("default_mode") or "auto").strip().lower()
    if mode not in REASONING_MODES:
        mode = "auto"
    efforts = list(dict.fromkeys(_string_list(raw.get("efforts"))))
    default_effort = str(raw.get("default_effort") or "").strip().lower() or None
    if default_effort not in efforts:
        default_effort = None
    adapter = str(raw.get("adapter") or "").strip().lower()
    if not adapter:
        # Backward compatibility for the first Octop reasoning-config draft.
        adapter = (
            "thinking_nested_effort"
            if raw.get("effort_parameter") == "thinking"
            else _legacy_adapter(model_id, base_url=base_url)
        )
    if adapter not in REASONING_ADAPTERS:
        adapter = "status_only"
    effort_type = str(raw.get("effort_type") or "enum").strip().lower()
    if effort_type not in EFFORT_TYPES:
        effort_type = "enum"
    toggle = bool(raw.get("toggle", True))
    if adapter == "status_only":
        toggle = False
        mode = "enabled"
        efforts = []
        default_effort = None
    return {
        "supported": True,
        "toggle": toggle,
        "default_mode": mode,
        "efforts": efforts,
        "default_effort": default_effort,
        "effort_type": effort_type,
        "adapter": adapter,
    }


def _selected_reasoning(
    capability: dict[str, Any], *, mode: str | None, effort: str | None
) -> tuple[str, str]:
    selected_mode = (mode or capability.get("default_mode") or "auto").strip().lower()
    if selected_mode not in REASONING_MODES:
        selected_mode = "auto"
    if not capability.get("toggle", True) and selected_mode == "disabled":
        selected_mode = "enabled"

    allowed_efforts = set(_string_list(capability.get("efforts")))
    selected_effort = (effort or capability.get("default_effort") or "").strip().lower()
    if selected_effort not in allowed_efforts:
        selected_effort = ""
    return selected_mode, selected_effort


def reasoning_request_parameters(
    capability: dict[str, Any] | None,
    *,
    mode: str | None,
    effort: str | None,
) -> dict[str, dict[str, Any]]:
    """Build model-field and request-body overrides for one provider adapter."""
    if capability is None:
        return {}
    selected_mode, selected_effort = _selected_reasoning(capability, mode=mode, effort=effort)
    adapter = capability.get("adapter")
    if adapter == "status_only":
        return {}

    model_fields: dict[str, Any] = {}
    extra_body: dict[str, Any] = {}

    if adapter == "openai_reasoning_effort":
        if selected_mode == "disabled":
            model_fields["reasoning_effort"] = "none"
        elif selected_effort:
            model_fields["reasoning_effort"] = selected_effort
    elif adapter == "anthropic_adaptive":
        if selected_mode == "enabled" or (selected_mode == "auto" and selected_effort):
            model_fields["thinking"] = {"type": "adaptive"}
        elif selected_mode == "disabled":
            model_fields["thinking"] = None
        if selected_effort and selected_mode != "disabled":
            model_fields["reasoning_effort"] = selected_effort
    elif adapter == "anthropic_budget":
        if selected_mode == "enabled" or (selected_mode == "auto" and selected_effort):
            budget = int(selected_effort) if selected_effort.isdigit() else 1024
            model_fields["thinking"] = {"type": "enabled", "budget_tokens": budget}
        elif selected_mode == "disabled":
            model_fields["thinking"] = None
    elif adapter == "dashscope":
        if selected_mode != "auto":
            extra_body["enable_thinking"] = selected_mode == "enabled"
        if selected_effort and selected_mode != "disabled":
            if capability.get("effort_type") == "token_budget" and selected_effort.isdigit():
                extra_body["thinking_budget"] = int(selected_effort)
            else:
                extra_body["reasoning_effort"] = selected_effort
    elif adapter == "openrouter":
        reasoning: dict[str, Any] = {}
        if selected_mode != "auto":
            reasoning["enabled"] = selected_mode == "enabled"
        if selected_effort and selected_mode != "disabled":
            reasoning["effort"] = selected_effort
        if reasoning:
            extra_body["reasoning"] = reasoning
    elif adapter in {"thinking", "thinking_nested_effort"}:
        if selected_mode != "auto":
            extra_body["thinking"] = {"type": selected_mode}
        if selected_effort:
            if adapter == "thinking_nested_effort":
                thinking = dict(extra_body.get("thinking") or {"type": "enabled"})
                thinking["reasoning_effort"] = selected_effort
                extra_body["thinking"] = thinking
            else:
                extra_body["reasoning_effort"] = selected_effort

    overrides: dict[str, dict[str, Any]] = {}
    if model_fields:
        overrides["model_fields"] = model_fields
    if extra_body:
        overrides["extra_body"] = extra_body
    return overrides


__all__ = [
    "EFFORT_TYPES",
    "REASONING_ADAPTERS",
    "reasoning_capability",
    "reasoning_request_parameters",
]
