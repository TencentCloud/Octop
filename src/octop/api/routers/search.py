"""Search-provider connectivity API (Settings → Models → Search)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.common.env_sync import reload_agents_after_env_change
from octop.api.deps import get_server, require_permission
from octop.infra.utils.env_file import (
    apply_env_file_replace,
    env_file_path,
    load_env_file,
    save_env_file,
)
from octop.infra.utils.search_probe import probe_search_provider
from octop.infra.websearch.config import (
    API_KEY_ENV,
    BASE_URL_ENV,
    is_default_deepseek_base_url,
    looks_like_deepseek_provider,
)

router = APIRouter(prefix="/search", tags=["search"])


class TestSearchRequest(BaseModel):
    env_vars: dict[str, str] = Field(
        ...,
        description="Provider env vars to use for this probe (not persisted).",
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
        description=(
            "auth_error | insufficient_balance | rate_limit | timeout | "
            "network_error | invalid_config | unknown"
        ),
    )


class ImportModelKeyResponse(BaseModel):
    ok: bool
    provider_name: str | None = None
    env_key: str | None = None
    base_url: str | None = Field(
        default=None,
        description="Search base URL copied from a custom (relay) provider, if any.",
    )
    error: str | None = None


@router.post(
    "/{provider_id}/test",
    response_model=TestSearchResponse,
    summary="Test search provider API key",
    description=(
        "Run a one-shot query against a web-search provider using the supplied "
        "env vars (TAVILY_API_KEY, BRAVE_API_KEY, DEEPSEEK_API_KEY / "
        "DEEPSEEK_SEARCH_API_KEY + DEEPSEEK_SEARCH_BASE_URL, GOOGLE_API_KEY + "
        "GOOGLE_CSE_ID, MOONSHOT_API_KEY, or TENCENTCLOUD_WSA_APIKEY). "
        "Credentials are not written to ~/.octop/env."
    ),
)
async def test_search_provider(
    provider_id: str,
    body: TestSearchRequest,
    _: Any = Depends(require_permission("search")),
) -> TestSearchResponse:
    result = await probe_search_provider(provider_id, body.env_vars)
    return TestSearchResponse(**result)


def _deepseek_model_provider(server: Any) -> Any | None:
    """Prefer an enabled DeepSeek model provider that has an API key."""
    services = getattr(server, "services", None)
    repo = getattr(services, "provider_repo", None)
    if repo is None:
        return None
    try:
        rows = repo.list_all()
    except Exception:  # pragma: no cover — corrupted provider table
        return None
    candidates = [
        row
        for row in rows
        if looks_like_deepseek_provider(
            getattr(row, "name", None),
            getattr(row, "base_url", None),
        )
        and str(getattr(row, "api_key", None) or "").strip()
    ]
    for row in candidates:
        if bool(getattr(row, "enabled", True)):
            return row
    return candidates[0] if candidates else None


@router.post(
    "/deepseek/import-model-key",
    response_model=ImportModelKeyResponse,
    summary="Reuse the DeepSeek model provider API key for web search",
    description=(
        "Copy the API key of the configured DeepSeek chat-model provider into "
        f"`{API_KEY_ENV}` in ~/.octop/env so Search / Fetch use the same key; a "
        f"custom provider base URL is copied into `{BASE_URL_ENV}`. The key "
        "itself is never returned to the client. Running agents reload in the "
        "background so the web_search / web_fetch tools are re-mounted. "
        "Requires the `search`, `envs` and `providers` permissions "
        "(the endpoint writes the global env file using a provider secret)."
    ),
)
async def import_deepseek_model_key(
    _search: Any = Depends(require_permission("search")),
    _envs: Any = Depends(require_permission("envs")),
    _providers: Any = Depends(require_permission("providers")),
    server: Any = Depends(get_server),
) -> ImportModelKeyResponse:
    row = _deepseek_model_provider(server)
    if row is None:
        return ImportModelKeyResponse(
            ok=False,
            error="No DeepSeek model provider with an API key is configured.",
        )
    api_key = str(getattr(row, "api_key", "") or "").strip()
    base_url = str(getattr(row, "base_url", "") or "").strip()
    updates: dict[str, str] = {API_KEY_ENV: api_key}
    if base_url and not is_default_deepseek_base_url(base_url):
        # Custom relay providers need their own API host; the key alone would
        # be sent to api.deepseek.com and fail.
        updates[BASE_URL_ENV] = base_url
    path = env_file_path(server.paths.root)
    previous = load_env_file(path)
    values = {**previous, **updates}
    save_env_file(path, values)
    apply_env_file_replace(path, previous=previous)
    reload_agents_after_env_change(server, previous, values)
    return ImportModelKeyResponse(
        ok=True,
        provider_name=str(getattr(row, "name", "") or "DeepSeek"),
        env_key=API_KEY_ENV,
        base_url=updates.get(BASE_URL_ENV),
    )
