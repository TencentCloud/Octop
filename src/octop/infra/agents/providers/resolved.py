"""Resolved model list across enabled providers."""

from __future__ import annotations

from typing import Any

from octop.infra.agents.providers.reasoning import reasoning_capability


def list_resolved_models(providers: list[Any]) -> list[dict[str, Any]]:
    """Return enabled models for providers that have credentials configured."""
    resolved: list[dict[str, Any]] = []
    for provider in providers:
        if not provider.enabled or not provider.api_key:
            continue
        for m in provider.get_models():
            if not m.get("enabled", True):
                continue
            # Catalogs may store either name; both feed the chat context ring.
            window = m.get("max_input_tokens") or m.get("context_window")
            resolved.append(
                {
                    "provider_id": provider.id,
                    "provider_name": provider.name,
                    "provider_kind": provider.kind,
                    "model": m["id"],
                    "name": m.get("name") or m["id"],
                    "input": m.get("input") or ["text"],
                    "reasoning": reasoning_capability(m, base_url=provider.base_url) is not None,
                    "reasoning_config": reasoning_capability(m, base_url=provider.base_url),
                    "context_window": window,
                    "max_tokens": m.get("max_tokens"),
                    "max_input_tokens": window,
                }
            )
    return resolved
