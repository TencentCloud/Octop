"""Unit tests for the DeepSeek Search / Fetch HTTP client."""

from __future__ import annotations

import json
import random
from typing import Any

import httpx
import pytest

from octop.infra.websearch.client import (
    DeepSeekSearchClient,
    DeepSeekSearchError,
    NoopLimiter,
    format_fetch_result,
    format_search_results,
)
from octop.infra.websearch.config import DeepSeekSearchConfig

API_KEY = "sk-test"
SEARCH_URL = "https://api.deepseek.com/v1/tools/search"
FETCH_URL = "https://api.deepseek.com/v1/tools/fetch"


def _client(
    handler: Any,
    *,
    max_attempts: int = 3,
    sleep: Any = None,
    rng: random.Random | None = None,
) -> tuple[DeepSeekSearchClient, list[float]]:
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    client = DeepSeekSearchClient(
        DeepSeekSearchConfig(api_key=API_KEY),
        transport=httpx.MockTransport(handler),
        max_attempts=max_attempts,
        sleep=sleep or fake_sleep,
        rng=rng or random.Random(0),
        search_limiter=NoopLimiter(),
        fetch_limiter=NoopLimiter(),
    )
    return client, delays


def _search_payload(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)


@pytest.mark.asyncio
async def test_search_sends_request_and_parses_results() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == SEARCH_URL
        assert request.headers["authorization"] == f"Bearer {API_KEY}"
        assert _search_payload(request) == {"query": "octop", "count": 10, "need_content": False}
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Low score",
                        "url": "https://low.test",
                        "snippet": "s",
                        "summary": "summary low",
                        "content": "",
                        "site_name": "Low",
                        "site_icon": None,
                        "date": None,
                        "rerank_score": 0.8,
                        "authority": 1,
                    },
                    {
                        "title": "High score",
                        "url": "https://high.test",
                        "snippet": "s",
                        "summary": "summary high",
                        "content": "",
                        "site_name": None,
                        "site_icon": None,
                        "date": "2026-06-01T00:00:00+00:00",
                        "rerank_score": 2.4,
                        "authority": 3,
                    },
                ]
            },
        )

    client, _delays = _client(handler)
    results = await client.search("octop")

    assert len(results) == 2
    assert [item.title for item in results] == ["High score", "Low score"]
    assert results[0].rerank_score == pytest.approx(2.4)
    assert results[0].authority == 3
    assert results[0].site_name == ""
    assert results[0].date == "2026-06-01T00:00:00+00:00"
    assert seen


@pytest.mark.asyncio
async def test_search_options_override_config_defaults() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = _search_payload(request)
        assert payload["count"] == 5
        assert payload["need_content"] is True
        assert payload["localization"] == "9.9.9.9"
        return httpx.Response(200, json={"results": []})

    client = DeepSeekSearchClient(
        DeepSeekSearchConfig(
            api_key=API_KEY,
            count=3,
            need_content=False,
            localization="1.1.1.1",
        ),
        transport=httpx.MockTransport(handler),
        search_limiter=NoopLimiter(),
        fetch_limiter=NoopLimiter(),
    )
    results = await client.search(
        "query",
        count=5,
        need_content=True,
        localization="9.9.9.9",
    )
    assert results == []


@pytest.mark.asyncio
async def test_search_rejects_invalid_queries_before_http() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request expected")

    client, _delays = _client(handler)
    with pytest.raises(DeepSeekSearchError) as empty_exc:
        await client.search("   ")
    assert empty_exc.value.error_type == "invalid_config"

    with pytest.raises(DeepSeekSearchError) as long_exc:
        await client.search("x" * 129)
    assert long_exc.value.error_type == "invalid_config"
    assert "128" in long_exc.value.message


@pytest.mark.asyncio
async def test_search_retries_429_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                429,
                headers={"retry-after": "1.5"},
                json={"error": {"message": "rate limited", "code": "rate_limit"}},
            )
        return httpx.Response(200, json={"results": [{"title": "ok", "url": "https://x.test"}]})

    client, delays = _client(handler)
    results = await client.search("q")
    assert calls["n"] == 2
    assert len(results) == 1
    assert delays == [1.5]


@pytest.mark.asyncio
async def test_search_429_exhausts_retries_with_readable_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "slow down"}})

    client, delays = _client(handler, max_attempts=2)
    with pytest.raises(DeepSeekSearchError) as exc:
        await client.search("q")
    assert exc.value.error_type == "rate_limited"
    assert exc.value.retryable is True
    assert len(delays) == 1
    assert "rate limit" in exc.value.readable()


@pytest.mark.asyncio
async def test_search_5xx_is_retried() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json={"results": []})

    client, delays = _client(handler)
    assert await client.search("q") == []
    assert calls["n"] == 3
    assert len(delays) == 2


@pytest.mark.asyncio
async def test_search_auth_error_is_not_retried() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    client, delays = _client(handler)
    with pytest.raises(DeepSeekSearchError) as exc:
        await client.search("q")
    assert calls["n"] == 1
    assert delays == []
    assert exc.value.error_type == "auth_error"
    assert "Settings" in exc.value.readable()


@pytest.mark.asyncio
async def test_search_network_error_surfaces() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client, delays = _client(handler, max_attempts=2)
    with pytest.raises(DeepSeekSearchError) as exc:
        await client.search("q")
    assert exc.value.error_type == "network_error"
    assert len(delays) == 1


@pytest.mark.asyncio
async def test_search_invalid_json_response() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    client, _delays = _client(handler)
    with pytest.raises(DeepSeekSearchError) as exc:
        await client.search("q")
    assert "non-JSON" in exc.value.message


@pytest.mark.asyncio
async def test_fetch_returns_title_and_markdown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == FETCH_URL
        assert _search_payload(request) == {"url": "https://example.com/a"}
        return httpx.Response(200, json={"title": "Example", "content": "# Hello"})

    client, _delays = _client(handler)
    page = await client.fetch("https://example.com/a")
    assert page.title == "Example"
    assert page.content == "# Hello"
    assert page.url == "https://example.com/a"


@pytest.mark.asyncio
async def test_fetch_rejects_unsafe_or_invalid_urls() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request expected")

    client, _delays = _client(handler)
    for url in ("", "ftp://example.com", "/relative", "https://user:pass@example.com", "x" * 8193):
        with pytest.raises(DeepSeekSearchError) as exc:
            await client.fetch(url)
        assert exc.value.error_type == "invalid_config"


@pytest.mark.asyncio
async def test_fetch_404_is_readable_and_not_retried() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, json={"error": {"message": "no content"}})

    client, delays = _client(handler)
    with pytest.raises(DeepSeekSearchError) as exc:
        await client.fetch("https://example.com/missing")
    assert calls["n"] == 1
    assert delays == []
    assert "could not extract" in exc.value.readable()


@pytest.mark.asyncio
async def test_fetch_empty_body_raises() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"title": "", "content": ""})

    client, _delays = _client(handler)
    with pytest.raises(DeepSeekSearchError) as exc:
        await client.fetch("https://example.com/empty")
    assert exc.value.error_type == "not_found"
    # A 200 response must not be reported as an HTTP 404.
    assert "HTTP 404" not in exc.value.readable()


def test_format_search_results_keeps_quality_signals() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError

    client, _delays = _client(handler)
    assert client.config.api_key == API_KEY

    from octop.infra.websearch.client import SearchResult

    rendered = format_search_results(
        "octop",
        [
            SearchResult(
                title="A result",
                url="https://example.com/a",
                summary="a summary",
                site_name="Example",
                date="2026-06-01",
                rerank_score=2.4,
                authority=3,
            )
        ],
    )
    assert "https://example.com/a" in rendered
    assert "rerank_score: 2.4/3" in rendered
    assert "authority: 3/4" in rendered
    assert "a summary" in rendered


def test_format_search_results_empty_and_truncated() -> None:
    assert "No web results found" in format_search_results("nothing", [])

    from octop.infra.websearch.client import SearchResult

    results = [
        SearchResult(title=f"Result {i}", url=f"https://example.com/{i}", summary="x" * 400)
        for i in range(10)
    ]
    rendered = format_search_results("q", results, max_chars=500)
    assert "truncated" in rendered
    assert "https://example.com/9" not in rendered


def test_format_fetch_result_truncates() -> None:
    from octop.infra.websearch.client import FetchResult

    rendered = format_fetch_result(
        FetchResult(url="https://example.com", title="T", content="y" * 100),
        max_chars=60,
    )
    assert rendered.startswith("Fetched page: T")
    assert "truncated" in rendered


@pytest.mark.asyncio
async def test_search_403_and_404_use_search_wording() -> None:
    for status, fragment in ((403, "rejected the search request"), (404, "search request failed")):

        def handler(_request: httpx.Request, _status: int = status) -> httpx.Response:
            return httpx.Response(_status, json={"error": {"message": "denied"}})

        client, delays = _client(handler)
        with pytest.raises(DeepSeekSearchError) as exc:
            await client.search("q")
        assert delays == []
        assert fragment in exc.value.readable()
        assert "page content" not in exc.value.readable()
        assert "fetch" not in exc.value.readable()


@pytest.mark.asyncio
async def test_fetch_403_keeps_fetch_wording() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "blocked by policy"}})

    client, _delays = _client(handler)
    with pytest.raises(DeepSeekSearchError) as exc:
        await client.fetch("https://example.com/blocked")
    assert exc.value.error_type == "forbidden"
    assert "refused to fetch" in exc.value.readable()


@pytest.mark.asyncio
async def test_search_retries_408() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(408, headers={"retry-after": "0"})
        return httpx.Response(200, json={"results": []})

    client, delays = _client(handler)
    assert await client.search("q") == []
    assert calls["n"] == 2
    assert delays == [0.0]


@pytest.mark.asyncio
async def test_qps_limiter_spaces_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.websearch import client as client_module

    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(client_module.asyncio, "sleep", fake_sleep)
    limiter = client_module.QpsLimiter(5.0)
    await limiter.acquire()
    await limiter.acquire()
    assert len(delays) == 1
    assert 0 < delays[0] <= 0.21
