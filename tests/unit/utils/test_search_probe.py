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
async def test_unknown_provider_includes_removed_legacy_ids() -> None:
    # brave / google were removed; probing them must report invalid_config.
    for legacy in ("brave", "google"):
        result = await search_probe.probe_search_provider(legacy, {})
        assert result["success"] is False
        assert result["error_type"] == "invalid_config"


@pytest.mark.asyncio
async def test_tavily_missing_key() -> None:
    result = await search_probe.probe_search_provider("tavily", {})
    assert result["success"] is False
    assert result["error_type"] == "invalid_config"
    assert "TAVILY_API_KEY" in (result.get("error") or "")


@pytest.mark.asyncio
async def test_doubao_missing_key() -> None:
    result = await search_probe.probe_search_provider("doubao", {})
    assert result["success"] is False
    assert result["error_type"] == "invalid_config"
    assert "DOUBAO_SEARCH_API_KEY" in (result.get("error") or "")


@pytest.mark.asyncio
async def test_deepseek_missing_key() -> None:
    result = await search_probe.probe_search_provider("deepseek", {})
    assert result["success"] is False
    assert result["error_type"] == "invalid_config"
    assert "DEEPSEEK_API_KEY" in (result.get("error") or "")


@pytest.mark.asyncio
async def test_exa_missing_key() -> None:
    result = await search_probe.probe_search_provider("exa", {})
    assert result["success"] is False
    assert result["error_type"] == "invalid_config"
    assert "EXA_API_KEY" in (result.get("error") or "")


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
async def test_doubao_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "open.feedcoopapi.com"
        assert request.url.path == "/search_api/global_search"
        assert request.headers.get("Authorization") == "Bearer doubao-key"
        body = request.read()
        assert b'"SearchType"' in body
        return httpx.Response(
            200,
            json={
                "ResponseMetadata": {"RequestId": "r1"},
                "Result": {
                    "TotalDocCount": 1,
                    "ErrorCode": 0,
                    "ErrorMsg": "",
                    "Documents": [
                        {"Title": "T", "Url": "https://example.com"},
                    ],
                },
            },
        )

    _patch_client(monkeypatch, httpx.MockTransport(handler))
    result = await search_probe.probe_search_provider(
        "doubao",
        {"DOUBAO_SEARCH_API_KEY": "doubao-key"},
    )
    assert result["success"] is True
    assert result["result_count"] == 1
    assert result["provider_id"] == "doubao"


@pytest.mark.asyncio
async def test_doubao_business_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ResponseMetadata": {"RequestId": "r2"},
                "Result": None,
                # API-layer error rides HTTP 200.
            }
            | {
                "ResponseMetadata": {
                    "RequestId": "r2",
                    "Error": {"Code": "700901", "Message": "APIKey invalid"},
                }
            },
        )

    _patch_client(monkeypatch, httpx.MockTransport(handler))
    result = await search_probe.probe_search_provider(
        "doubao",
        {"DOUBAO_SEARCH_API_KEY": "bad"},
    )
    assert result["success"] is False
    assert result["error_type"] == "auth_error"
    assert "700901" in (result.get("error") or "")


@pytest.mark.asyncio
async def test_doubao_quota_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ResponseMetadata": {"RequestId": "r3"},
                "Result": {"ErrorCode": 10406, "ErrorMsg": "quota exhausted"},
            },
        )

    _patch_client(monkeypatch, httpx.MockTransport(handler))
    result = await search_probe.probe_search_provider(
        "doubao",
        {"DOUBAO_SEARCH_API_KEY": "key"},
    )
    assert result["success"] is False
    assert result["error_type"] == "auth_error"
    assert "10406" in (result.get("error") or "")


@pytest.mark.asyncio
async def test_deepseek_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.deepseek.com"
        assert request.url.path == "/v1/tools/search"
        assert request.headers.get("Authorization") == "Bearer ds-key"
        return httpx.Response(
            200,
            json={"results": [{"title": "T", "url": "https://example.com"}]},
        )

    _patch_client(monkeypatch, httpx.MockTransport(handler))
    result = await search_probe.probe_search_provider(
        "deepseek",
        {"DEEPSEEK_API_KEY": "ds-key"},
    )
    assert result["success"] is True
    assert result["result_count"] == 1
    assert result["provider_id"] == "deepseek"


@pytest.mark.asyncio
async def test_exa_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.exa.ai"
        assert request.url.path == "/search"
        assert request.headers.get("x-api-key") == "exa-key"
        return httpx.Response(
            200,
            json={"results": [{"title": "T", "url": "https://example.com"}]},
        )

    _patch_client(monkeypatch, httpx.MockTransport(handler))
    result = await search_probe.probe_search_provider(
        "exa",
        {"EXA_API_KEY": "exa-key"},
    )
    assert result["success"] is True
    assert result["result_count"] == 1
    assert result["provider_id"] == "exa"
