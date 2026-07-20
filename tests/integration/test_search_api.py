"""Integration tests for POST /api/search/{provider_id}/test."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch


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
