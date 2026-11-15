"""Search-provider catalog, endpoint configuration, and connectivity API."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.env_file import (
    apply_env_file_replace,
    env_file_path,
    load_env_file,
    save_env_file,
)
from octop.infra.utils.search_probe import probe_search_provider
from octop.infra.utils.search_providers import (
    SEARCH_PROVIDERS,
    get_search_provider,
)

router = APIRouter(prefix="/search", tags=["search"])

_MAX_ENDPOINT_LENGTH = 2048


class TestSearchRequest(BaseModel):
    env_vars: dict[str, str] = Field(
        ...,
        description="Provider env vars to use for this probe (not persisted).",
    )
    endpoint: str | None = Field(
        default=None,
        description="Optional DeepSeek endpoint override for this probe only.",
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


class SearchProviderInfo(BaseModel):
    id: str
    env_vars: list[str]
    optional_env_vars: list[str]
    personal_key: bool
    endpoint_env: str | None = None
    label_key: str = ""


class SearchProvidersResponse(BaseModel):
    providers: list[SearchProviderInfo]


class SearchEndpointBody(BaseModel):
    endpoint: str | None = Field(
        default=None,
        max_length=_MAX_ENDPOINT_LENGTH,
        description="Global endpoint URL, or null to clear it.",
    )


class SearchEndpointResponse(BaseModel):
    provider_id: str
    endpoint_env: str
    endpoint: str | None = None


def _write_global_env(server: Any, key: str, value: str | None) -> None:
    path = env_file_path(server.paths.root)
    previous = load_env_file(path)
    values = dict(previous)
    if value:
        values[key] = value
    else:
        values.pop(key, None)
    save_env_file(path, values)
    apply_env_file_replace(path, previous=previous)


def _validate_endpoint(endpoint: str) -> str:
    """Validate the administrator-configured endpoint URL shape.

    LAN/private gateways are supported: the administrator is the only
    configurator, so no DNS or SSRF host checks are applied. Only https, a
    valid host/port, no embedded credentials, and the length limit are
    enforced.
    """
    text = endpoint.strip()
    if not text or len(text) > _MAX_ENDPOINT_LENGTH:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "endpoint must be 1 to 2048 characters")
    # ``urlparse`` strips tabs/newlines before parsing but callers would still
    # persist the original text; whitespace/control characters also break the
    # ``~/.octop/env`` line format (a newline can inject extra keys).
    if any(ch.isspace() or ord(ch) < 0x20 or ch == "\x7f" for ch in text):
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            "endpoint must not contain whitespace or control characters",
        )
    parsed = urlparse(text)
    if parsed.scheme != "https":
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "endpoint must use https")
    if parsed.username or parsed.password:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "endpoint must not contain credentials")
    if not parsed.hostname:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "endpoint is missing a hostname")
    try:
        port = parsed.port
    except ValueError as exc:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid port: {exc}") from exc
    if port == 0:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "endpoint port must be between 1 and 65535")
    return text


@router.get(
    "/providers",
    summary="Search provider catalog",
    response_model=SearchProvidersResponse,
)
async def list_search_providers(
    _: Any = Depends(require_permission("search")),
    server: Any = Depends(get_server),
) -> SearchProvidersResponse:
    """Catalog plus the administrator-configured global endpoints."""
    providers = [
        SearchProviderInfo(
            id=spec.id,
            env_vars=list(spec.env_vars),
            optional_env_vars=list(spec.optional_env_vars),
            personal_key=spec.personal_key,
            endpoint_env=spec.endpoint_env,
            label_key=spec.label_key,
        )
        for spec in SEARCH_PROVIDERS
    ]
    return SearchProvidersResponse(providers=providers)


@router.put(
    "/{provider_id}/endpoint",
    summary="Set the global search endpoint",
    response_model=SearchEndpointResponse,
)
async def set_search_endpoint(
    provider_id: str,
    body: SearchEndpointBody,
    _: Any = Depends(require_permission("search")),
    server: Any = Depends(get_server),
) -> SearchEndpointResponse:
    """Persist (or clear) the administrator's endpoint for one provider."""
    spec = get_search_provider(provider_id)
    if spec is None or not spec.endpoint_env:
        raise OctopError(ErrorCode.NOT_FOUND, "search provider has no configurable endpoint")
    endpoint = _validate_endpoint(body.endpoint) if body.endpoint else None
    _write_global_env(server, spec.endpoint_env, endpoint)
    return SearchEndpointResponse(
        provider_id=spec.id,
        endpoint_env=spec.endpoint_env,
        endpoint=endpoint,
    )


@router.post(
    "/{provider_id}/test",
    response_model=TestSearchResponse,
    summary="Test search provider API key",
    description=(
        "Run a one-shot query against a web-search provider using the supplied "
        "env vars (TAVILY_API_KEY, BRAVE_API_KEY, DEEPSEEK_API_KEY, "
        "GOOGLE_API_KEY + GOOGLE_CSE_ID, MOONSHOT_API_KEY, or "
        "TENCENTCLOUD_WSA_APIKEY). Credentials are not written to ~/.octop/env."
    ),
)
async def test_search_provider(
    provider_id: str,
    body: TestSearchRequest,
    _: Any = Depends(require_permission("search")),
) -> TestSearchResponse:
    endpoint = _validate_endpoint(body.endpoint) if body.endpoint else None
    result = await probe_search_provider(provider_id, body.env_vars, endpoint=endpoint)
    return TestSearchResponse(**result)
