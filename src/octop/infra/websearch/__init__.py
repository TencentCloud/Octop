"""DeepSeek web Search / Fetch provider (built-in third-party search source)."""

from __future__ import annotations

from octop.infra.websearch.config import (
    API_KEY_ENV,
    BASE_URL_ENV,
    COUNT_ENV,
    DEFAULT_BASE_URL,
    FALLBACK_API_KEY_ENV,
    LOCALIZATION_ENV,
    NEED_CONTENT_ENV,
    DeepSeekSearchConfig,
)
from octop.infra.websearch.tools import (
    DEEPSEEK_WEB_TOOLS,
    HARNESS_DEEPSEEK_TOOL,
    WEB_FETCH_TOOL,
    WEB_SEARCH_TOOL,
    DeepSeekWebTools,
    build_deepseek_web_tools,
    harness_deepseek_provider_available,
)

__all__ = [
    "API_KEY_ENV",
    "BASE_URL_ENV",
    "COUNT_ENV",
    "DEFAULT_BASE_URL",
    "DEEPSEEK_WEB_TOOLS",
    "HARNESS_DEEPSEEK_TOOL",
    "FALLBACK_API_KEY_ENV",
    "LOCALIZATION_ENV",
    "NEED_CONTENT_ENV",
    "WEB_FETCH_TOOL",
    "WEB_SEARCH_TOOL",
    "DeepSeekSearchConfig",
    "DeepSeekWebTools",
    "build_deepseek_web_tools",
    "harness_deepseek_provider_available",
]
