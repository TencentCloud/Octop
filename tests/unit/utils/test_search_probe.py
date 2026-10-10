"""Unit tests for search-provider HTTP probes."""

from __future__ import annotations

import httpx
import pytest

from octop.infra.utils import search_probe


def _patch_client(monkeypatch: pytest.MonkeyPatch, handler: httpx.MockTransport) -> None:
    real = httpx.AsyncClient

    def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs = dict(kwargs)
        kwargs["transport"] = handler
        return real(*args, **kwargs)

    monkeypatch.setattr(search_probe.httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_unknown_provider() -> None:
    result = await search_probe.probe_search_provider("nope", {})
    assert result["success"] is False
    assert result["error_type"] == "invalid_config"
    assert result["provider_id"] == "nope"


@pytest.mark.asyncio
async def test_tavily_missing_key() -> None:
    result = await search_probe.probe_search_provider("tavily", {})
    assert result["success"] is False
    assert result["error_type"] == "invalid_config"
    assert "TAVILY_API_KEY" in (result.get("error") or "")


@pytest.mark.asyncio
async def test_google_missing_cse() -> None:
    result = await search_probe.probe_search_provider("google", {"GOOGLE_API_KEY": "gk"})
    assert result["success"] is False
    assert "GOOGLE_CSE_ID" in (result.get("error") or "")


@pytest.mark.asyncio
async def test_tavily_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.tavily.com"
        assert request.headers.get("Authorization") == "Bearer tvly-test"
        return httpx.Response(200, json={"results": [{"url": "https://example.com"}]})

    _patch_client(monkeypatch, httpx.MockTransport(handler))
    result = await search_probe.probe_search_provider(
        "tavily",
        {"TAVILY_API_KEY": "tvly-test"},
    )
    assert result["success"] is True
    assert result["result_count"] == 1
    assert result["provider_id"] == "tavily"


@pytest.mark.asyncio
async def test_tavily_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid api key")

    _patch_client(monkeypatch, httpx.MockTransport(handler))
    result = await search_probe.probe_search_provider(
        "tavily",
        {"TAVILY_API_KEY": "bad"},
    )
    assert result["success"] is False
    assert result["error_type"] == "auth_error"


@pytest.mark.asyncio
async def test_brave_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.search.brave.com"
        assert request.headers.get("X-Subscription-Token") == "brave-key"
        return httpx.Response(
            200,
            json={"web": {"results": [{"url": "https://example.com"}]}},
        )

    _patch_client(monkeypatch, httpx.MockTransport(handler))
    result = await search_probe.probe_search_provider(
        "brave",
        {"BRAVE_API_KEY": "brave-key"},
    )
    assert result["success"] is True
    assert result["result_count"] == 1


@pytest.mark.parametrize("override", [None, "draft-key"])
async def test_saved_credentials_probe_uses_environment_without_mutating_it(
    monkeypatch: pytest.MonkeyPatch, override: str | None
) -> None:
    monkeypatch.setenv("BRAVE_API_KEY", "saved-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Subscription-Token"] == (override or "saved-key")
        return httpx.Response(200, json={"web": {"results": []}})

    _patch_client(monkeypatch, httpx.MockTransport(handler))
    result = await search_probe.probe_search_provider(
        "brave",
        {"BRAVE_API_KEY": override} if override is not None else {},
        use_saved_credentials=True,
    )
    assert result["success"]
    assert search_probe.os.environ["BRAVE_API_KEY"] == "saved-key"
    assert "saved-key" not in str(result)


async def test_draft_probe_does_not_use_saved_key_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BRAVE_API_KEY", "saved-key")
    result = await search_probe.probe_search_provider("brave", {})
    assert result["success"] is False
    assert result["error_type"] == "invalid_config"
