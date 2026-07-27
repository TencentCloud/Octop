"""Built-in provider template loading (harness-agent bundles)."""

from __future__ import annotations

from typing import Any


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
                    {
                        "id": "gpt-5.6-sol",
                        "name": "GPT-5.6 Sol",
                        "enabled": True,
                        "input": ["text"],
                    },
                    {
                        "id": "gpt-5.6-terra",
                        "name": "GPT-5.6 Terra",
                        "enabled": True,
                        "input": ["text"],
                    },
                    {
                        "id": "gpt-5.6-luna",
                        "name": "GPT-5.6 Luna",
                        "enabled": True,
                        "input": ["text"],
                    },
                ],
                "logo_id": "openai",
            },
        )
    return out
