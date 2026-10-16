"""Search-provider connectivity API (Settings → Advanced → Search)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.agents.settings.search import (
    CustomSearchProviderUpdate,
    CustomSearchSettings,
    CustomSearchSettingsStore,
    CustomSearchSettingsUpdate,
)
from octop.infra.utils.locale import resolve_request_locale
from octop.infra.utils.search_probe import probe_search_provider

router = APIRouter(prefix="/search", tags=["search"])


class TestSearchRequest(BaseModel):
    env_vars: dict[str, str] = Field(
        ...,
        description="Provider env vars to use for this probe (not persisted).",
    )
    use_saved_credentials: bool = Field(
        False,
        description="Use the server's configured search credentials; supplied env vars override them.",
    )


class TestSearchResponse(BaseModel):
    success: bool
    provider_id: str
    response_time_ms: int
    result_count: int | None = None
    message: str | None = None
    error: str | None = None
    error_type: str | None = Field(
        None,
        description="auth_error | timeout | network_error | invalid_config | unknown",
    )


class TestCustomSearchRequest(BaseModel):
    provider: CustomSearchProviderUpdate = Field(
        description="Provider configuration to probe without saving it."
    )


@router.get(
    "/custom",
    response_model=CustomSearchSettings,
    summary="Get custom search engine settings",
    description=(
        "Return instance-wide custom HTTP/JSON search engines and the selected search source. "
        "active_provider_id is a custom engine ID, preset:tavily, preset:brave, "
        "preset:google, preset:kimi, or null for built-in search only. "
        "Requires the search permission. Stored API keys are never returned."
    ),
)
async def get_custom_search_settings(
    _: Any = Depends(require_permission("search")),
    server: Any = Depends(get_server),
) -> CustomSearchSettings:
    store: CustomSearchSettingsStore = server.app_runtime.agent_registry.search_settings
    return await asyncio.get_running_loop().run_in_executor(None, store.load)


@router.put(
    "/custom",
    response_model=CustomSearchSettings,
    summary="Replace custom search engine settings",
    description=(
        "Replace the complete custom engine list, then reload running agents. "
        "Requires the search permission. Select one custom engine ID or a configured "
        "preset via preset:tavily, preset:brave, preset:google, or preset:kimi. "
        "Set active_provider_id to null to explicitly use built-in search only, even "
        "when preset credentials are configured. Changing the selection retains "
        "preset credentials and custom engines included in the submitted list. API keys "
        "are write-only: omit or pass null to keep a stored key; pass an empty string "
        "to clear it. Removing an engine also removes its stored key. Header, query "
        "parameter, and JSON body strings support {query}, {max_results}, and {api_key} "
        "templates; JSON paths select the "
        "result array and each result's title, URL, and content."
    ),
)
async def put_custom_search_settings(
    body: CustomSearchSettingsUpdate,
    request: Request,
    _: Any = Depends(require_permission("search")),
    server: Any = Depends(get_server),
) -> CustomSearchSettings:
    registry = server.app_runtime.agent_registry
    store: CustomSearchSettingsStore = registry.search_settings
    locale = resolve_request_locale(request)
    view = await asyncio.get_running_loop().run_in_executor(
        None, lambda: store.save(body, locale=locale)
    )
    await registry.reload_all()
    return view


@router.post(
    "/custom/test",
    response_model=TestSearchResponse,
    summary="Test a custom search engine configuration",
    description=(
        "Run a one-shot query with an unsaved HTTP/JSON engine configuration. "
        "Requires the search permission. A null or omitted API key uses the stored "
        "key for the provider ID, when present. Neither configuration nor credentials "
        "are persisted by this operation."
    ),
)
async def test_custom_search_provider(
    body: TestCustomSearchRequest,
    request: Request,
    _: Any = Depends(require_permission("search")),
    server: Any = Depends(get_server),
) -> TestSearchResponse:
    result = await server.app_runtime.agent_registry.search_settings.probe(
        body.provider, locale=resolve_request_locale(request)
    )
    return TestSearchResponse(**result)


@router.post(
    "/{provider_id}/test",
    response_model=TestSearchResponse,
    summary="Test search provider API key",
    description=(
        "Run a one-shot query against a web-search provider using the supplied "
        "env vars (TAVILY_API_KEY, BRAVE_API_KEY, GOOGLE_API_KEY + GOOGLE_CSE_ID, "
        "or MOONSHOT_API_KEY). Set use_saved_credentials to probe the configured "
        "engine, including credentials supplied through the server environment. "
        "Credentials are not written to ~/.octop/env."
    ),
)
async def test_search_provider(
    provider_id: str,
    body: TestSearchRequest,
    _: Any = Depends(require_permission("search")),
) -> TestSearchResponse:
    result = await probe_search_provider(
        provider_id, body.env_vars, use_saved_credentials=body.use_saved_credentials
    )
    return TestSearchResponse(**result)
