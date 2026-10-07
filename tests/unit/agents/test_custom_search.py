"""Custom search probes and agent calls must use the same configured endpoint."""

from __future__ import annotations

import json

import httpx
import pytest

from octop.infra.agents.search_tools import build_custom_search_tools
from octop.infra.utils import custom_search
from octop.infra.utils.env_file import search_env_changed
from octop.infra.utils.search_probe import probe_search_provider


@pytest.mark.parametrize("protocol", ["tavily", "qianfan"])
async def test_probe_and_runtime_use_custom_endpoint(
    monkeypatch: pytest.MonkeyPatch, protocol: str
) -> None:
    env = {
        "CUSTOM_SEARCH_URL": "https://search.example/v2/search",
        "CUSTOM_SEARCH_API_KEY": "test-key",
        "CUSTOM_SEARCH_PROTOCOL": protocol,
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    guarded: list[str] = []

    async def guard(url: str) -> None:
        guarded.append(url)

    monkeypatch.setattr(custom_search, "validate_https_url_resolved", guard)
    queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == env["CUSTOM_SEARCH_URL"]
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        if protocol == "qianfan":
            queries.append(body["messages"][0]["content"])
            assert body["resource_type_filter"][0]["type"] == "web"
        else:
            queries.append(body["query"])
        return httpx.Response(
            200,
            json={
                "references" if protocol == "qianfan" else "results": [
                    {"title": "result", "url": "https://example.com"}
                ]
            },
        )

    real = httpx.AsyncClient

    def factory(**kwargs: object) -> httpx.AsyncClient:
        return real(**{**kwargs, "transport": httpx.MockTransport(handler)})

    monkeypatch.setattr(custom_search.httpx, "AsyncClient", factory)
    result = await probe_search_provider("custom", env)
    assert result["success"] is True
    assert result["result_count"] == 1
    tools = build_custom_search_tools()
    assert len(tools) == 1
    answer = json.loads(await tools[0].ainvoke({"query": "actual query"}))
    assert answer["results"][0]["title"] == "result"
    assert queries[-1] == "actual query"
    assert guarded == [env["CUSTOM_SEARCH_URL"]] * 2


async def test_custom_search_rejects_private_endpoint() -> None:
    result = await probe_search_provider(
        "custom", {"CUSTOM_SEARCH_URL": "https://127.0.0.1/search", "CUSTOM_SEARCH_API_KEY": "key"}
    )
    assert result["success"] is False
    assert result["error_type"] == "invalid_config"


@pytest.mark.parametrize(
    "key", ["CUSTOM_SEARCH_URL", "CUSTOM_SEARCH_API_KEY", "CUSTOM_SEARCH_PROTOCOL"]
)
def test_custom_search_changes_reload_agents(key: str) -> None:
    assert search_env_changed({key: "old"}, {key: "new"})


def test_incomplete_custom_search_is_not_mounted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOM_SEARCH_API_KEY", "key")
    monkeypatch.delenv("CUSTOM_SEARCH_URL", raising=False)
    assert build_custom_search_tools() == []
