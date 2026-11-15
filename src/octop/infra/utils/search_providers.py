"""Catalog of built-in web-search providers and their credential env vars.

Single source of truth for the self-service search-key API, the admin probe,
and the harness mounting list. Keep it in sync with
``octop_harness.builtin.tools.web_search``; ``personal_key=False`` marks
providers that need no user credential.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchProviderSpec:
    """One web-search provider exposed to users and admins."""

    id: str
    env_vars: tuple[str, ...]
    optional_env_vars: tuple[str, ...] = ()
    personal_key: bool = True
    endpoint_env: str | None = None
    label_key: str = ""


SEARCH_PROVIDERS: tuple[SearchProviderSpec, ...] = (
    SearchProviderSpec(
        id="tavily",
        env_vars=("TAVILY_API_KEY",),
        label_key="searchKeys.providers.tavily",
    ),
    SearchProviderSpec(
        id="brave",
        env_vars=("BRAVE_API_KEY",),
        label_key="searchKeys.providers.brave",
    ),
    SearchProviderSpec(
        id="deepseek",
        env_vars=("DEEPSEEK_API_KEY",),
        endpoint_env="DEEPSEEK_SEARCH_ENDPOINT",
        label_key="searchKeys.providers.deepseek",
    ),
    SearchProviderSpec(
        id="google",
        env_vars=("GOOGLE_API_KEY", "GOOGLE_CSE_ID"),
        label_key="searchKeys.providers.google",
    ),
    SearchProviderSpec(
        id="kimi",
        env_vars=("MOONSHOT_API_KEY",),
        label_key="searchKeys.providers.kimi",
    ),
    SearchProviderSpec(
        id="yuanbao",
        env_vars=("TENCENTCLOUD_WSA_APIKEY",),
        label_key="searchKeys.providers.yuanbao",
    ),
    SearchProviderSpec(
        id="you",
        env_vars=(),
        optional_env_vars=("YDC_API_KEY",),
        label_key="searchKeys.providers.you",
    ),
    SearchProviderSpec(
        id="searchfree",
        env_vars=(),
        personal_key=False,
        label_key="searchKeys.providers.searchfree",
    ),
)

SEARCH_PROVIDERS_BY_ID: dict[str, SearchProviderSpec] = {spec.id: spec for spec in SEARCH_PROVIDERS}

SEARCH_PROVIDER_IDS: tuple[str, ...] = tuple(spec.id for spec in SEARCH_PROVIDERS)


def get_search_provider(provider_id: str) -> SearchProviderSpec | None:
    """Return the catalog entry for *provider_id*, or ``None`` when unknown."""
    return SEARCH_PROVIDERS_BY_ID.get(provider_id)


def personal_search_providers() -> tuple[SearchProviderSpec, ...]:
    """Providers that accept a user-supplied credential."""
    return tuple(spec for spec in SEARCH_PROVIDERS if spec.personal_key)


__all__ = [
    "SEARCH_PROVIDERS",
    "SEARCH_PROVIDERS_BY_ID",
    "SEARCH_PROVIDER_IDS",
    "SearchProviderSpec",
    "get_search_provider",
    "personal_search_providers",
]
