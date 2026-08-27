"""Built-in provider template loading (harness-agent bundles)."""

from __future__ import annotations

from typing import Any


def _reasoning_profile(provider_id: str, model_id: str) -> dict[str, Any] | None:
    """Reasoning metadata for bundled models with documented request semantics."""
    provider = provider_id.lower()
    model = model_id.lower()
    enum_efforts = ["low", "medium", "high"]

    if provider in {"openai", "openai-codex"} and (
        model.startswith("gpt-5") or model in {"o3", "o4-mini"}
    ):
        efforts = enum_efforts if model in {"o3", "o4-mini"} else ["minimal", *enum_efforts]
        if model.startswith(("gpt-5.4", "gpt-5.5")):
            efforts.append("xhigh")
        can_disable = model.startswith(("gpt-5.2", "gpt-5.4", "gpt-5.5"))
        return {
            "supported": True,
            "adapter": "openai_reasoning_effort",
            "toggle": can_disable,
            "default_mode": "auto" if can_disable else "enabled",
            "efforts": efforts,
            "default_effort": "medium",
        }

    if provider == "anthropic" and model.startswith(("claude-sonnet-4", "claude-opus-4")):
        return {
            "supported": True,
            "adapter": "anthropic_budget",
            "toggle": True,
            "default_mode": "auto",
            "effort_type": "token_budget",
            "efforts": ["1024", "4096", "8192", "16384"],
            "default_effort": "4096",
        }

    if provider == "gemini" and model.startswith("gemini-") and not model.startswith("gemini-2.0"):
        mandatory = model.startswith("gemini-3") or model == "gemini-2.5-pro"
        return {
            "supported": True,
            "adapter": "openai_reasoning_effort",
            "toggle": not mandatory,
            "default_mode": "enabled" if mandatory else "auto",
            "efforts": enum_efforts,
            "default_effort": "high" if mandatory else "medium",
        }

    if provider == "groq" and "gpt-oss" in model:
        return {
            "supported": True,
            "adapter": "openai_reasoning_effort",
            "toggle": False,
            "default_mode": "enabled",
            "efforts": enum_efforts,
            "default_effort": "medium",
        }

    if provider.startswith("tencent-"):
        if model.startswith("minimax-"):
            return {
                "supported": True,
                "adapter": "status_only",
                "toggle": False,
                "default_mode": "enabled",
            }
        if model.startswith("deepseek-v4-"):
            return {
                "supported": True,
                "adapter": "thinking_nested_effort"
                if provider
                in {
                    "tencent-token-plan",
                    "tencent-token-plan-enterprise-cn",
                    "tencent-coding-plan",
                }
                else "thinking",
                "toggle": True,
                "default_mode": "enabled",
                "efforts": ["high", "max"],
                "default_effort": "high",
            }
        if model.startswith(("glm-", "kimi-")) or model == "tc-code-latest":
            return {
                "supported": True,
                "adapter": "thinking",
                "toggle": True,
                "default_mode": "enabled",
            }
        if provider == "tencent-hy-token-plan" and model.startswith("hy3"):
            return {
                "supported": True,
                "adapter": "status_only",
                "toggle": False,
                "default_mode": "enabled",
            }

    if provider == "deepseek":
        if model == "deepseek-reasoner":
            return {
                "supported": True,
                "adapter": "status_only",
                "toggle": False,
                "default_mode": "enabled",
            }
        if model.startswith("deepseek-v4-"):
            return {
                "supported": True,
                "adapter": "thinking",
                "toggle": True,
                "default_mode": "auto",
                "efforts": ["high", "max"],
                "default_effort": "high",
            }

    if provider.startswith("zhipu-") and model.startswith(("glm-4.7", "glm-5")):
        return {
            "supported": True,
            "adapter": "thinking",
            "toggle": True,
            "default_mode": "auto",
        }

    if provider.startswith(("dashscope", "aliyun-")):
        if model.startswith("minimax-") or "-thinking-" in model:
            return {
                "supported": True,
                "adapter": "status_only",
                "toggle": False,
                "default_mode": "enabled",
            }
        if model.startswith(("qwen3", "glm-", "kimi-", "deepseek-")):
            return {
                "supported": True,
                "adapter": "dashscope",
                "toggle": True,
                "default_mode": "auto",
            }

    if provider.startswith("kimi-") and (
        model in {"kimi-k2.5", "kimi-k2.6"} or "thinking" in model
    ):
        dedicated = "thinking" in model
        return {
            "supported": True,
            "adapter": "status_only" if dedicated else "thinking",
            "toggle": not dedicated,
            "default_mode": "enabled" if dedicated else "auto",
        }

    if provider.startswith("minimax-") and model.startswith("minimax-m2"):
        return {
            "supported": True,
            "adapter": "status_only",
            "toggle": False,
            "default_mode": "enabled",
        }

    if provider == "openrouter" and model.startswith(("anthropic/claude-", "google/gemini-2.5")):
        return {
            "supported": True,
            "adapter": "openrouter",
            "toggle": True,
            "default_mode": "auto",
            "efforts": enum_efforts,
            "default_effort": "medium",
        }

    if provider.startswith("opencode-"):
        if model.startswith("minimax-"):
            return {
                "supported": True,
                "adapter": "status_only",
                "toggle": False,
                "default_mode": "enabled",
            }
        if model.startswith(("claude-opus-4-6", "claude-sonnet-4-6")):
            return {
                "supported": True,
                "adapter": "anthropic_adaptive",
                "toggle": True,
                "default_mode": "auto",
                "efforts": ["low", "medium", "high", "max"],
                "default_effort": "high",
            }
        if model == "grok-4.5" or model == "glm-5.2":
            efforts = (
                ["minimal", "low", "medium", "high", "xhigh", "max"]
                if model == "glm-5.2"
                else enum_efforts
            )
            return {
                "supported": True,
                "adapter": "openai_reasoning_effort",
                "toggle": model != "grok-4.5",
                "default_mode": "enabled" if model == "grok-4.5" else "auto",
                "efforts": efforts,
                "default_effort": "high",
            }
        if model.startswith(("deepseek-v4-", "kimi-k", "glm-5.1")):
            return {
                "supported": True,
                "adapter": "thinking",
                "toggle": True,
                "default_mode": "auto",
            }

    return None


def load_provider_presets() -> list[dict[str, Any]]:
    """Serialize harness-agent provider templates for API / CLI."""
    from importlib import resources

    from harness_agent.providers import load_provider_templates, serialize_provider_preset

    bundled = resources.files("harness_agent.providers").joinpath("provider_template.json")
    out = [serialize_provider_preset(p) for p in load_provider_templates(str(bundled))]
    if not any(p.get("id") == "openai-codex" for p in out):
        out.insert(
            0,
            {
                "id": "openai-codex",
                "name": "OpenAI (ChatGPT)",
                "base_url": "https://chatgpt.com/backend-api/codex",
                "protocol": "openai",
                "api_key_prefix": "",
                "auth_method": "codex_oauth",
                "models": [
                    {"id": "gpt-5.4", "name": "GPT-5.4", "enabled": True, "input": ["text"]},
                    {
                        "id": "gpt-5.4-mini",
                        "name": "GPT-5.4 mini",
                        "enabled": True,
                        "input": ["text"],
                    },
                    {"id": "gpt-5.5", "name": "GPT-5.5", "enabled": True, "input": ["text"]},
                ],
                "logo_id": "openai",
            },
        )
    if not any(p.get("id") == "onnx" for p in out):
        from octop.infra.agents.providers.onnx_catalog import ONNX_PRESET_MODEL_IDS

        onnx_preset = {
            "id": "onnx",
            "name": "ONNX (Local)",
            "base_url": "",
            "protocol": "openai",
            "api_key_prefix": "",
            "models": [
                {
                    "id": mid,
                    "name": mid,
                    "enabled": False,
                    "embedding": True,
                    "task": "embedding",
                    "input": ["text"],
                }
                for mid in ONNX_PRESET_MODEL_IDS
            ],
            "logo_id": "onnx",
        }
        insert_at = next(
            (i + 1 for i, p in enumerate(out) if p.get("id") == "ollama"),
            len(out),
        )
        out.insert(insert_at, onnx_preset)
    for preset in out:
        provider_id = str(preset.get("id") or "")
        for model in preset.get("models") or []:
            profile = _reasoning_profile(provider_id, str(model.get("id") or ""))
            if profile is not None:
                model["reasoning"] = True
                model["reasoning_config"] = profile
    return out
