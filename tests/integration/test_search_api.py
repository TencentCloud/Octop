"""Integration tests for POST /api/search/{provider_id}/test."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx

from octop.api.app import build_app


async def test_search_test_requires_auth(env: Any) -> None:
    c, _srv, _auth = env
    r = await c.post("/api/search/tavily/test", json={"env_vars": {}})
    assert r.status_code == 401


async def test_search_test_unknown_provider(env: Any) -> None:
    c, _srv, auth = env
    r = await c.post(
        "/api/search/nope/test",
        headers=auth,
        json={"env_vars": {}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["provider_id"] == "nope"
    assert body["error_type"] == "invalid_config"


async def test_search_test_tavily_ok(env: Any) -> None:
    c, _srv, auth = env
    with patch(
        "octop.infra.utils.search_probe._tavily",
        new=AsyncMock(
            return_value={
                "success": True,
                "result_count": 1,
                "message": "ok",
            }
        ),
    ):
        r = await c.post(
            "/api/search/tavily/test",
            headers=auth,
            json={"env_vars": {"TAVILY_API_KEY": "tvly-x"}},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["provider_id"] == "tavily"
    assert body["result_count"] == 1
    assert isinstance(body["response_time_ms"], int)


async def test_custom_search_probe_and_api_docs(env: Any) -> None:
    c, _srv, auth = env
    with patch(
        "octop.infra.utils.search_probe.request_custom_search",
        new=AsyncMock(return_value={"results": [{"url": "https://example.com"}]}),
    ) as probe:
        r = await c.post(
            "/api/search/custom/test",
            headers=auth,
            json={
                "env_vars": {
                    "CUSTOM_SEARCH_URL": "https://search.example/search",
                    "CUSTOM_SEARCH_API_KEY": "key",
                    "CUSTOM_SEARCH_PROTOCOL": "qianfan",
                }
            },
        )
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert r.json()["result_count"] == 1
    assert probe.call_args.args[0]["CUSTOM_SEARCH_PROTOCOL"] == "qianfan"
    _srv.services = replace(
        _srv.services, config=replace(_srv.services.config, enable_api_docs=True)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=build_app(_srv)), base_url="http://testserver"
    ) as docs_client:
        docs = await docs_client.get("/api/docs", headers=auth)
        assert docs.status_code == 200
        schema = (await docs_client.get("/api/openapi.json", headers=auth)).json()
    operation = schema["paths"]["/api/search/{provider_id}/test"]["post"]
    assert operation["summary"]
    assert "CUSTOM_SEARCH_PROTOCOL" in operation["description"]
    assert "TestSearchResponse" in str(operation["responses"]["200"])
