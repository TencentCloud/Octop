"""Custom HTTP search providers, encrypted credentials, and runtime tool."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from octop.i18n import tr
from octop.infra.connectors.crypto import decrypt_credentials, encrypt_credentials
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.errors import ErrorCode, OctopError

_SETTINGS_KEY = "custom_search_providers"
_CREDENTIALS_KEY = "custom_search_credentials"
_TIMEOUT = 30.0
_PRESET_KEYS: dict[str, tuple[str, ...]] = {
    "tavily": ("TAVILY_API_KEY",),
    "brave": ("BRAVE_API_KEY",),
    "google": ("GOOGLE_API_KEY", "GOOGLE_CSE_ID"),
    "kimi": ("MOONSHOT_API_KEY",),
}


def _preset_configured(provider_id: str) -> bool:
    return all(os.environ.get(key, "").strip() for key in _PRESET_KEYS[provider_id])


def _legacy_search_selection() -> str | None:
    return next(
        (
            f"preset:{provider_id}"
            for provider_id in _PRESET_KEYS
            if _preset_configured(provider_id)
        ),
        None,
    )


class CustomSearchProviderConfig(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$", description="Stable provider ID.")
    name: str = Field(min_length=1, description="User-defined display name.")
    url: str = Field(min_length=1, description="HTTP(S) JSON search endpoint, including its path.")
    method: Literal["GET", "POST"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP header templates.")
    params: dict[str, str] = Field(
        default_factory=lambda: {"q": "{query}", "format": "json"},
        description="Query parameters; supports {query}, {max_results}, and {api_key}.",
    )
    body: dict[str, Any] = Field(
        default_factory=lambda: {"query": "{query}", "max_results": "{max_results}"},
        description="POST JSON body templates, including nested objects and arrays.",
    )
    results_path: str = Field("results", description="Dot path to results; empty for a root array.")
    title_path: str = Field(
        "title", description="Dot path within each result; empty to use its URL."
    )
    url_path: str = Field("url", min_length=1, description="Dot path to each result URL.")
    content_path: str = Field("content", description="Dot path to result text; empty to omit.")


class CustomSearchProvider(CustomSearchProviderConfig):
    api_key_set: bool = False


class CustomSearchProviderUpdate(CustomSearchProviderConfig):
    api_key: str | None = Field(
        None, description="Omit/null to retain the saved key; empty string to clear it."
    )


class CustomSearchSettings(BaseModel):
    providers: list[CustomSearchProvider] = Field(default_factory=list)
    configured_preset_ids: list[str] = Field(
        default_factory=list,
        description="Presets with available credentials, including keys from process environment. No keys are returned.",
    )
    active_provider_id: str | None = Field(
        None,
        description=(
            "Active engine: a custom provider ID or preset:tavily/brave/google/kimi. "
            "Null selects built-in search and disables all configured third-party engines."
        ),
    )


class CustomSearchSettingsUpdate(BaseModel):
    providers: list[CustomSearchProviderUpdate]
    active_provider_id: str | None = Field(
        None,
        description="Custom ID or preset:tavily/brave/google/kimi; null enables only built-in search.",
    )


class _SearchArguments(BaseModel):
    query: str = Field(min_length=1, description="Search query.")
    max_results: int = Field(5, ge=1, le=20, description="Maximum results to return.")


class _SearchFailure(Exception):
    def __init__(self, key: str, error_type: str, *, locale: str, **kwargs: object) -> None:
        super().__init__(tr(f"search.{key}", locale, **kwargs))
        self.error_type = error_type


def _validate_provider(provider: CustomSearchProviderConfig, api_key: str, locale: str) -> None:
    try:
        url = urlsplit(provider.url)
        valid_url = url.scheme in {"http", "https"} and bool(url.hostname) and not url.username
        _ = url.port
    except ValueError:
        valid_url = False
    if not valid_url:
        raise _SearchFailure("invalid_url", "invalid_config", locale=locale)
    query_data = [provider.params, provider.body if provider.method == "POST" else {}]
    if "{query}" not in json.dumps(query_data):
        raise _SearchFailure("missing_query", "invalid_config", locale=locale)
    templates = json.dumps([provider.headers, *query_data])
    if "{api_key}" in templates and not api_key:
        raise _SearchFailure("api_key_required", "invalid_config", locale=locale)


def _render(value: Any, *, query: str, max_results: int, api_key: str) -> Any:
    if isinstance(value, str):
        if value == "{max_results}":
            return max_results
        replacements = {"query": query, "max_results": str(max_results), "api_key": api_key}
        return re.sub(
            r"\{(query|max_results|api_key)\}",
            lambda match: replacements[match[1]],
            value,
        )
    if isinstance(value, dict):
        return {
            key: _render(item, query=query, max_results=max_results, api_key=api_key)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _render(item, query=query, max_results=max_results, api_key=api_key) for item in value
        ]
    return value


def _at_path(value: Any, path: str) -> Any:
    if not path:
        return value
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and re.fullmatch(r"\d+", part):
            index = int(part)
            value = value[index] if index < len(value) else None
        else:
            return None
    return value


async def _search(
    provider: CustomSearchProviderConfig,
    api_key: str,
    query: str,
    max_results: int,
    locale: str,
) -> list[dict[str, str]]:
    _validate_provider(provider, api_key, locale)
    if not query.strip():
        raise _SearchFailure("empty_query", "invalid_config", locale=locale)

    def render(value: Any) -> Any:
        return _render(value, query=query, max_results=max_results, api_key=api_key)

    headers = {key: str(render(value)) for key, value in provider.headers.items()}
    params = {key: str(render(value)) for key, value in provider.params.items()}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.request(
                provider.method,
                provider.url,
                headers=headers,
                params=params,
                json=render(provider.body) if provider.method == "POST" else None,
            )
    except httpx.TimeoutException as exc:
        raise _SearchFailure("timeout", "timeout", locale=locale) from exc
    except httpx.HTTPError as exc:
        raise _SearchFailure("network_error", "network_error", locale=locale) from exc
    except (ValueError, httpx.InvalidURL) as exc:
        raise _SearchFailure("invalid_request", "invalid_config", locale=locale) from exc
    if response.status_code >= 400:
        error_type = "auth_error" if response.status_code in {401, 403, 429} else "network_error"
        raise _SearchFailure("http_error", error_type, locale=locale, status=response.status_code)
    try:
        payload = response.json()
    except ValueError as exc:
        raise _SearchFailure("invalid_json", "unknown", locale=locale) from exc
    items = _at_path(payload, provider.results_path)
    if not isinstance(items, list):
        raise _SearchFailure("results_array", "invalid_config", locale=locale)
    results: list[dict[str, str]] = []
    for item in items[:max_results]:
        url = _at_path(item, provider.url_path)
        title = _at_path(item, provider.title_path) if provider.title_path else None
        content = _at_path(item, provider.content_path) if provider.content_path else None
        if (
            not isinstance(item, dict)
            or not isinstance(url, str)
            or not url.strip()
            or (title is not None and not isinstance(title, str))
            or (content is not None and not isinstance(content, str))
        ):
            raise _SearchFailure("invalid_result", "invalid_config", locale=locale)
        results.append({"title": title or url, "url": url, "content": content or ""})
    return results


class CustomSearchSettingsStore:
    def __init__(self, *, settings_repo: SettingsRepo, secret_repo: SecretRepo) -> None:
        self._settings = settings_repo
        self._secrets = secret_repo

    def _credentials(self) -> dict[str, str]:
        blob = self._secrets.get(_CREDENTIALS_KEY)
        if blob is None:
            return {}
        return dict(decrypt_credentials(self._secrets, blob)["api_keys"])

    def load(self) -> CustomSearchSettings:
        configured_presets = [
            preset_id for preset_id in _PRESET_KEYS if _preset_configured(preset_id)
        ]
        raw = self._settings.get(_SETTINGS_KEY)
        if not raw:
            return CustomSearchSettings(
                providers=[],
                configured_preset_ids=configured_presets,
                active_provider_id=_legacy_search_selection(),
            )
        payload = json.loads(raw)
        view = CustomSearchSettings.model_validate(payload)
        view.configured_preset_ids = configured_presets
        if view.active_provider_id is None and not payload.get("selection_explicit"):
            view.active_provider_id = _legacy_search_selection()
        if view.active_provider_id and view.active_provider_id.startswith("preset:"):
            preset_id = view.active_provider_id.removeprefix("preset:")
            if preset_id not in _PRESET_KEYS or not _preset_configured(preset_id):
                view.active_provider_id = None
        keys = self._credentials()
        for provider in view.providers:
            provider.api_key_set = bool(keys.get(provider.id))
        return view

    def save(
        self, update: CustomSearchSettingsUpdate, *, locale: str = "en"
    ) -> CustomSearchSettings:
        ids = [provider.id for provider in update.providers]
        if len(ids) != len(set(ids)):
            reason = tr("search.duplicate_ids", locale)
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, reason, details={"reason": reason})
        selected = update.active_provider_id
        if (
            selected is not None
            and selected not in ids
            and selected not in {f"preset:{provider_id}" for provider_id in _PRESET_KEYS}
        ):
            reason = tr("search.invalid_active", locale)
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, reason, details={"reason": reason})
        if (
            selected is not None
            and selected.startswith("preset:")
            and not _preset_configured(selected.removeprefix("preset:"))
        ):
            reason = tr("search.preset_unconfigured", locale)
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, reason, details={"reason": reason})
        previous_keys = self._credentials()
        keys: dict[str, str] = {}
        providers: list[CustomSearchProvider] = []
        for provider in update.providers:
            key = (
                previous_keys.get(provider.id, "") if provider.api_key is None else provider.api_key
            )
            try:
                _validate_provider(provider, key, locale)
            except _SearchFailure as exc:
                raise OctopError(
                    ErrorCode.SLASH_BAD_ARGS, str(exc), details={"reason": str(exc)}
                ) from exc
            if key:
                keys[provider.id] = key
            providers.append(
                CustomSearchProvider(
                    **provider.model_dump(exclude={"api_key"}), api_key_set=bool(key)
                )
            )
        blob = encrypt_credentials(self._secrets, {"api_keys": keys})
        self._secrets.get_or_create(_CREDENTIALS_KEY, lambda: blob)
        self._secrets.rotate(_CREDENTIALS_KEY, blob)
        view = CustomSearchSettings(
            providers=providers, active_provider_id=update.active_provider_id
        )
        self._settings.set(
            _SETTINGS_KEY,
            json.dumps(
                {**view.model_dump(exclude={"configured_preset_ids"}), "selection_explicit": True},
                ensure_ascii=False,
            ),
        )
        return self.load()

    def harness_search_policy(self) -> list[str]:
        selected = self.load().active_provider_id
        if selected is not None and selected.startswith("preset:"):
            return [selected.removeprefix("preset:")]
        return ["searchfree"]

    async def probe(
        self, provider: CustomSearchProviderUpdate, *, locale: str = "en"
    ) -> dict[str, Any]:
        started = time.perf_counter()
        if provider.api_key is None:
            credentials = await asyncio.get_running_loop().run_in_executor(None, self._credentials)
            key = credentials.get(provider.id, "")
        else:
            key = provider.api_key
        try:
            results = await asyncio.wait_for(
                _search(provider, key, "octop connectivity probe", 1, locale), timeout=_TIMEOUT
            )
            outcome: dict[str, Any] = {"success": True, "result_count": len(results)}
        except _SearchFailure as exc:
            outcome = {"success": False, "error": str(exc), "error_type": exc.error_type}
        except TimeoutError:
            outcome = {
                "success": False,
                "error": tr("search.timeout", locale),
                "error_type": "timeout",
            }
        return {
            "provider_id": provider.id,
            "response_time_ms": int((time.perf_counter() - started) * 1000),
            **outcome,
        }

    def build_tool(self) -> StructuredTool | None:
        view = self.load()
        provider = next(
            (item for item in view.providers if item.id == view.active_provider_id), None
        )
        if provider is None:
            return None
        key = self._credentials().get(provider.id, "")

        async def search(query: str, max_results: int = 5) -> str:
            try:
                results = await asyncio.wait_for(
                    _search(provider, key, query, max_results, "en"), timeout=_TIMEOUT
                )
                return json.dumps({"results": results}, ensure_ascii=False)
            except _SearchFailure as exc:
                return json.dumps({"error": str(exc)}, ensure_ascii=False)
            except TimeoutError:
                return json.dumps({"error": tr("search.timeout", "en")})

        return StructuredTool.from_function(
            coroutine=search,
            name="custom_search",
            description=tr("search.tool_description", "en", name=provider.name),
            args_schema=_SearchArguments,
        )
