"""Admin search catalog and global endpoint configuration."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_search_endpoint_env() -> Iterator[None]:
    """Keep DEEPSEEK_SEARCH_ENDPOINT from leaking into other tests' probes."""
    os.environ.pop("DEEPSEEK_SEARCH_ENDPOINT", None)
    yield
    os.environ.pop("DEEPSEEK_SEARCH_ENDPOINT", None)


async def test_provider_catalog_is_exposed(env: Any) -> None:
    c, _srv, auth = env
    r = await c.get("/api/search/providers", headers=auth)
    assert r.status_code == 200
    body = r.json()
    ids = {item["id"] for item in body["providers"]}
    assert {"tavily", "brave", "deepseek", "google", "kimi", "yuanbao", "you", "searchfree"} == ids
    deepseek = next(item for item in body["providers"] if item["id"] == "deepseek")
    assert deepseek["endpoint_env"] == "DEEPSEEK_SEARCH_ENDPOINT"


async def test_endpoint_round_trip_persists_to_env_file(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, srv, auth = env
    monkeypatch.delenv("DEEPSEEK_SEARCH_ENDPOINT", raising=False)
    endpoint = "https://search.example.com/v1/tools/search"

    r = await c.put(
        "/api/search/deepseek/endpoint",
        headers=auth,
        json={"endpoint": endpoint},
    )
    assert r.status_code == 200
    assert r.json()["endpoint"] == endpoint

    env_file = srv.paths.root / "env"
    assert f"DEEPSEEK_SEARCH_ENDPOINT={endpoint}" in env_file.read_text(encoding="utf-8")
    assert os.environ["DEEPSEEK_SEARCH_ENDPOINT"] == endpoint

    r = await c.put(
        "/api/search/deepseek/endpoint",
        headers=auth,
        json={"endpoint": None},
    )
    assert r.status_code == 200
    assert r.json()["endpoint"] is None
    assert "DEEPSEEK_SEARCH_ENDPOINT" not in env_file.read_text(encoding="utf-8")
    assert "DEEPSEEK_SEARCH_ENDPOINT" not in os.environ


async def test_endpoint_validation(env: Any) -> None:
    c, _srv, auth = env

    r = await c.put(
        "/api/search/deepseek/endpoint",
        headers=auth,
        json={"endpoint": "http://search.example.com/v1"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"

    r = await c.put(
        "/api/search/deepseek/endpoint",
        headers=auth,
        json={"endpoint": "https://search.example.com:bad/v1"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"

    # Whitespace / control characters must not reach ``~/.octop/env``: a
    # newline would inject extra keys when the env file is parsed back.
    for bad in (
        "https://search.example.com/v1\nPATH=/evil",
        "https://search.example.com/v1\tPATH=/evil",
        "https://ho st/v1",
    ):
        r = await c.put(
            "/api/search/deepseek/endpoint",
            headers=auth,
            json={"endpoint": bad},
        )
        assert r.status_code == 400, bad
        assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"

    r = await c.put(
        "/api/search/tavily/endpoint",
        headers=auth,
        json={"endpoint": "https://search.example.com/v1"},
    )
    assert r.status_code == 404


async def test_private_endpoint_is_accepted(env: Any) -> None:
    c, _srv, auth = env
    endpoint = "https://192.168.1.10/search"

    r = await c.put(
        "/api/search/deepseek/endpoint",
        headers=auth,
        json={"endpoint": endpoint},
    )
    assert r.status_code == 200
    assert r.json()["endpoint"] == endpoint


async def test_endpoint_config_requires_search_permission(env: Any) -> None:
    c, _srv, _auth = env
    r = await c.put(
        "/api/search/deepseek/endpoint",
        json={"endpoint": "https://search.example.com/v1"},
    )
    assert r.status_code == 401


async def test_admin_probe_accepts_a_private_custom_endpoint(env: Any) -> None:
    c, _srv, auth = env
    endpoint = "https://192.168.1.10/search"
    ok = {
        "success": True,
        "provider_id": "deepseek",
        "response_time_ms": 1,
        "result_count": 1,
        "message": "ok",
    }
    with patch(
        "octop.api.routers.search.probe_search_provider",
        new=AsyncMock(return_value=ok),
    ) as probe:
        r = await c.post(
            "/api/search/deepseek/test",
            headers=auth,
            json={
                "env_vars": {"DEEPSEEK_API_KEY": "sk"},
                "endpoint": endpoint,
            },
        )
    assert r.status_code == 200
    assert probe.await_args.kwargs["endpoint"] == endpoint

    r = await c.post(
        "/api/search/deepseek/test",
        headers=auth,
        json={"env_vars": {"DEEPSEEK_API_KEY": "sk"}, "endpoint": "http://192.168.1.10/"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"
