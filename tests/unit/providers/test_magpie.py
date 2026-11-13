"""Magpie identity, discovery, and catalog sync."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from octop.infra.agents.providers.magpie import (
    MAGPIE_DEFAULT_BASE_URL,
    MAGPIE_HELLO_URL,
    MAGPIE_LOCAL_API_KEY,
    MAGPIE_SESSION_HEADER,
    discover_local_magpie,
    ensure_magpie_headers,
    initial_magpie_models,
    is_magpie_default_base_url,
    is_magpie_provider,
    magpie_catalog_model,
    magpie_preset,
    plan_magpie_sync,
)


def test_preset_is_empty_openai_catalog() -> None:
    preset = magpie_preset()
    assert preset["id"] == "magpie"
    assert preset["name"] == "Magpie"
    assert preset["protocol"] == "openai"
    assert preset["base_url"] == MAGPIE_DEFAULT_BASE_URL
    assert preset["models"] == []
    assert preset["default_api_key"] == MAGPIE_LOCAL_API_KEY
    assert preset["integration"] == "magpie"


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("http://127.0.0.1:3425/v1", True),
        ("http://127.0.0.1:3425/v1/", True),
        ("https://127.0.0.1:3425/v1", False),
        ("http://localhost:3425/v1", False),
        ("http://127.0.0.1:3426/v1", False),
        ("http://127.0.0.1:3425/v1/extra", False),
        ("http://127.0.0.1/v1", False),
        ("http://magpie.example/v1", False),
    ],
)
def test_default_base_url_matches_scheme_host_port_and_path(base_url: str, expected: bool) -> None:
    assert is_magpie_default_base_url(base_url) is expected


def test_identity_prefers_integration_then_name_then_exact_url() -> None:
    assert is_magpie_provider(
        provider_name="custom",
        base_url="https://gateway.example/v1",
        extra={"integration": "magpie"},
    )
    assert is_magpie_provider(provider_name="Magpie", base_url="https://other.example/v1")
    assert is_magpie_provider(provider_name="custom", base_url="http://127.0.0.1:3425/v1")
    assert not is_magpie_provider(
        provider_name="my-magpie-gateway", base_url="https://api.example/v1"
    )
    assert not is_magpie_provider(
        provider_name="OpenCode Go", base_url="https://opencode.ai/zen/go/v1"
    )


def test_headers_add_user_agent_and_keep_overrides() -> None:
    from octop import __version__

    headers = ensure_magpie_headers(None)
    assert headers["User-Agent"] == f"Octop/{__version__}"
    assert MAGPIE_SESSION_HEADER not in headers

    custom = ensure_magpie_headers({"user-agent": "Mine/1", "X-Magpie-Session": "keep"})
    assert custom["user-agent"] == "Mine/1"
    assert custom["X-Magpie-Session"] == "keep"

    probe = ensure_magpie_headers({}, probe=True)
    assert probe[MAGPIE_SESSION_HEADER]
    assert probe[MAGPIE_SESSION_HEADER] != "thread"


def test_catalog_keeps_nested_ids_and_skips_non_chat() -> None:
    kept = magpie_catalog_model(
        {
            "id": "vendor/org/model",
            "display_name": "Shown",
            "context_window": 128000,
            "max_output_tokens": 4096,
            "modalities": ["text", "image", "embedding"],
            "reasoning_config": {"supported": True, "adapter": "thinking"},
        }
    )
    assert kept == {
        "id": "vendor/org/model",
        "name": "Shown",
        "context_window": 128000,
        "max_tokens": 4096,
        "input": ["text", "image"],
        "reasoning": True,
        "reasoning_config": {"supported": True, "adapter": "thinking"},
    }
    assert magpie_catalog_model({"id": "group/route", "modalities": ["text"]}) == {
        "id": "group/route",
        "name": "group/route",
        "input": ["text"],
    }
    assert magpie_catalog_model(
        {
            "id": "codex/gpt-6.1-sol",
            "display_name": "GPT-6.1-Sol",
            "type": "model",
            "context_window": 500000,
            "max_output_tokens": 128000,
            "modalities": {"input": ["text", "image"]},
            "reasoning": True,
        }
    ) == {
        "id": "codex/gpt-6.1-sol",
        "name": "GPT-6.1-Sol",
        "context_window": 500000,
        "max_tokens": 128000,
        "input": ["text", "image"],
        "reasoning": True,
    }
    assert magpie_catalog_model({"id": "text-embedding-3-large", "type": "embedding"}) is None
    assert magpie_catalog_model({"id": "video-model", "type": "video"}) is None
    assert magpie_catalog_model(
        {"id": "mystery", "reasoning_config": {"adapter": "not-a-real-adapter"}}
    ) == {"id": "mystery", "name": "mystery"}


def test_duplicate_ids_and_empty_catalog() -> None:
    assert initial_magpie_models([]) is None
    created = initial_magpie_models(
        [
            {"id": "a/b/c", "name": "A"},
            {"id": "a/b/c", "name": "dup"},
            {"id": "group/x", "name": "G"},
        ]
    )
    assert created is not None
    assert [model["id"] for model in created] == ["a/b/c", "group/x"]
    assert all(model["enabled"] is True for model in created)


def test_sync_preserves_overrides_and_lists_removals() -> None:
    existing = [
        {
            "id": "keep/me",
            "name": "Old",
            "enabled": False,
            "input": ["text", "image"],
            "context_window": 1000,
            "visibility": "groups",
            "group_ids": ["design"],
        },
        {"id": "gone", "name": "Gone", "enabled": True, "visibility": "all"},
    ]
    fetched = [
        {"id": "keep/me", "name": "New name", "context_window": 999999, "input": ["text"]},
        {"id": "keep/me", "name": "dup"},
        {"id": "added/one", "name": "Added"},
    ]
    plan = plan_magpie_sync(existing, fetched)
    assert plan.added == ["added/one"]
    assert plan.removed == ["gone"]
    kept = plan.models[0]
    assert kept["enabled"] is False
    assert kept["input"] == ["text", "image"]
    assert kept["context_window"] == 1000
    assert kept["group_ids"] == ["design"]
    assert kept["name"] == "Old"
    assert plan.models[1]["id"] == "added/one"
    assert plan.models[1]["enabled"] is False


def test_empty_refresh_removes_every_model() -> None:
    plan = plan_magpie_sync([{"id": "a", "enabled": True}, {"id": "b", "enabled": True}], [])
    assert plan.models == []
    assert plan.removed == ["a", "b"]
    assert plan.added == []


class _HelloClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def __aenter__(self) -> _HelloClient:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def get(self, url: str) -> httpx.Response:
        assert url == MAGPIE_HELLO_URL
        responder = self.kwargs["responder"]
        result = responder()
        if isinstance(result, Exception):
            raise result
        return result


def _response(
    status: int, payload: Any | None = None, *, text: str | None = None
) -> httpx.Response:
    request = httpx.Request("GET", MAGPIE_HELLO_URL)
    if text is not None:
        return httpx.Response(status, text=text, request=request)
    return httpx.Response(status, json=payload, request=request)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("responder", "available", "version"),
    [
        (lambda: _response(200, {"name": "magpie", "version": "1.2.3"}), True, "1.2.3"),
        (lambda: _response(200, {"name": "other", "version": "1"}), False, None),
        (lambda: _response(200, text="not-json"), False, None),
        (lambda: _response(302, {"name": "magpie"}), False, None),
        (lambda: _response(500, {"name": "magpie"}), False, None),
        (lambda: httpx.ConnectError("connection refused"), False, None),
        (lambda: httpx.TimeoutException("timed out"), False, None),
    ],
)
async def test_discover_local_magpie(
    monkeypatch: pytest.MonkeyPatch,
    responder: Any,
    available: bool,
    version: str | None,
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    created: list[_HelloClient] = []

    def factory(**kwargs: Any) -> _HelloClient:
        client = _HelloClient(**kwargs, responder=responder)
        created.append(client)
        return client

    monkeypatch.setattr("httpx.AsyncClient", factory)
    found = await discover_local_magpie()
    assert found.available is available
    assert found.base_url == MAGPIE_DEFAULT_BASE_URL
    assert found.version == version
    assert created[0].kwargs["follow_redirects"] is False
    assert created[0].kwargs["trust_env"] is False
    assert created[0].kwargs["timeout"] == 1.0
