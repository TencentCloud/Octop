"""Configuration for the DeepSeek web Search / Fetch provider.

Values live in the global ``~/.octop/env`` file (Admin → Models → Search), so a
search provider can be switched without rebuilding an agent; saving a search
key triggers a background agent reload (see ``api/routers/envs.py``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

# The bundled DeepSeek chat-model provider uses the same API key, so search
# falls back to the conventional ``DEEPSEEK_API_KEY``. An explicitly configured
# search-only key wins because it states the intended scope.
API_KEY_ENV = "DEEPSEEK_API_KEY"
FALLBACK_API_KEY_ENV = "DEEPSEEK_SEARCH_API_KEY"
BASE_URL_ENV = "DEEPSEEK_SEARCH_BASE_URL"
COUNT_ENV = "DEEPSEEK_SEARCH_COUNT"
NEED_CONTENT_ENV = "DEEPSEEK_SEARCH_NEED_CONTENT"
LOCALIZATION_ENV = "DEEPSEEK_SEARCH_LOCALIZATION"

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_COUNT = 10
MIN_COUNT = 1
MAX_COUNT = 50
# DeepSeek Search limits ``query`` to 1–128 Unicode characters, Fetch ``url`` to
# 8192 characters.
MAX_QUERY_CHARS = 128
MAX_FETCH_URL_CHARS = 8192

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off", ""})


def parse_bool(raw: object, *, default: bool = False) -> bool:
    """Parse an env-style boolean (``true``/``1``/``yes``/``on``)."""
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    return default


def clamp_count(raw: object) -> int:
    """Clamp the configured result count into DeepSeek's 1–50 range."""
    try:
        value = int(str(raw).strip()) if raw is not None and str(raw).strip() else DEFAULT_COUNT
    except (TypeError, ValueError):
        return DEFAULT_COUNT
    return max(MIN_COUNT, min(MAX_COUNT, value))


def resolve_base_url(raw: object) -> str:
    """Normalize the API base URL (accepts a trailing slash or ``/v1``)."""
    value = str(raw).strip() if raw is not None else ""
    value = value.rstrip("/")
    return value or DEFAULT_BASE_URL


def search_endpoint(base_url: str) -> str:
    """``POST {base}/v1/tools/search`` (``…/v1`` accepted for convenience)."""
    base = resolve_base_url(base_url)
    if base.endswith("/v1"):
        return f"{base}/tools/search"
    return f"{base}/v1/tools/search"


def fetch_endpoint(base_url: str) -> str:
    """``POST {base}/v1/tools/fetch``."""
    base = resolve_base_url(base_url)
    if base.endswith("/v1"):
        return f"{base}/tools/fetch"
    return f"{base}/v1/tools/fetch"


def is_default_deepseek_base_url(base_url: object) -> bool:
    """True when *base_url* points at DeepSeek's own API host (or is unset)."""
    raw = str(base_url or "").strip()
    if not raw:
        return True
    try:
        host = (urlsplit(raw).hostname or "").lower()
    except ValueError:
        return False
    return host == "api.deepseek.com"


def looks_like_deepseek_provider(name: object, base_url: object) -> bool:
    """True when a model-provider row points at the DeepSeek API.

    Used by the one-click "reuse the DeepSeek model provider key" flow; the
    provider ``kind`` is always ``openai`` for the bundled preset, so the name
    and the API host are the only stable markers.
    """
    provider_name = str(name or "").strip().lower()
    if provider_name == "deepseek" or provider_name.startswith(("deepseek ", "deepseek-")):
        return True
    raw = str(base_url or "").strip()
    if not raw:
        return False
    try:
        host = (urlsplit(raw).hostname or "").lower()
    except ValueError:
        return False
    return host == "api.deepseek.com" or host.endswith(".deepseek.com")


@dataclass(frozen=True)
class DeepSeekSearchConfig:
    """Resolved DeepSeek Search / Fetch settings for one agent build."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    count: int = DEFAULT_COUNT
    need_content: bool = False
    localization: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> DeepSeekSearchConfig | None:
        """Build a config from env vars; ``None`` when no API key is configured."""
        # Explicit search-only key wins; otherwise reuse the conventional key.
        api_key = str(env.get(FALLBACK_API_KEY_ENV) or "").strip()
        if not api_key:
            api_key = str(env.get(API_KEY_ENV) or "").strip()
        if not api_key:
            return None
        return cls(
            api_key=api_key,
            base_url=resolve_base_url(env.get(BASE_URL_ENV)),
            count=clamp_count(env.get(COUNT_ENV)),
            need_content=parse_bool(env.get(NEED_CONTENT_ENV)),
            localization=str(env.get(LOCALIZATION_ENV) or "").strip(),
        )

    @property
    def search_url(self) -> str:
        return search_endpoint(self.base_url)

    @property
    def fetch_url(self) -> str:
        return fetch_endpoint(self.base_url)


__all__ = [
    "API_KEY_ENV",
    "BASE_URL_ENV",
    "COUNT_ENV",
    "DEFAULT_BASE_URL",
    "DEFAULT_COUNT",
    "FALLBACK_API_KEY_ENV",
    "LOCALIZATION_ENV",
    "MAX_COUNT",
    "MAX_FETCH_URL_CHARS",
    "MAX_QUERY_CHARS",
    "MIN_COUNT",
    "NEED_CONTENT_ENV",
    "DeepSeekSearchConfig",
    "clamp_count",
    "fetch_endpoint",
    "is_default_deepseek_base_url",
    "looks_like_deepseek_provider",
    "parse_bool",
    "resolve_base_url",
    "search_endpoint",
]
