"""Search-provider connectivity API (Settings → Advanced → Search)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import current_admin
from octop.infra.utils.search_probe import probe_search_provider

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
        description="auth_error | timeout | network_error | invalid_config | unknown",
    )


@router.post(
    "/{provider_id}/test",
    response_model=TestSearchResponse,
    summary="Test search provider API key",
    description=(
        "Run a one-shot query against a web-search provider using the supplied "
        "env vars (TAVILY_API_KEY, BRAVE_API_KEY, GOOGLE_API_KEY + GOOGLE_CSE_ID, "
        "or MOONSHOT_API_KEY). Credentials are not written to ~/.octop/env."
    ),
)
async def test_search_provider(
    provider_id: str,
    body: TestSearchRequest,
    _: Any = Depends(current_admin),
) -> TestSearchResponse:
    result = await probe_search_provider(provider_id, body.env_vars)
    return TestSearchResponse(**result)
