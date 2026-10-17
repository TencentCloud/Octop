"""Unit tests for search-provider HTTP probes."""

from __future__ import annotations

import json

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


@pytest.fixture(autouse=True)
def _clear_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # The resolver falls back to the process environment; keep tests hermetic.
    monkeypatch.delenv(search_probe.KIMI_MODEL_ENV, raising=False)


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


# ---------------------------------------------------------------------------
# Kimi (Moonshot) — model configurability and error clarity (#1926)
# ---------------------------------------------------------------------------


def _kimi_handler(
    response: httpx.Response,
    seen: dict[str, object],
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["body"] = json.loads(request.content)
        return response

    return httpx.MockTransport(handler)


def test_kimi_search_model_prefers_request_body() -> None:
    assert search_probe.kimi_search_model({"MOONSHOT_SEARCH_MODEL": " kimi-k3 "}) == "kimi-k3"


def test_kimi_search_model_falls_back_to_environ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(search_probe.KIMI_MODEL_ENV, "kimi-k2.7-code")
    assert search_probe.kimi_search_model({}) == "kimi-k2.7-code"


def test_kimi_search_model_defaults_when_unset() -> None:
    assert search_probe.kimi_search_model({}) == search_probe.DEFAULT_KIMI_MODEL


@pytest.mark.asyncio
async def test_kimi_uses_current_model_and_omits_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retired ``moonshot-v1-128k`` must be gone, and so must ``temperature``.

    Moonshot pins ``temperature`` server-side on every current model and
    rejects anything else with HTTP 400.
    """
    seen: dict[str, object] = {}
    handler = _kimi_handler(
        httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        ),
        seen,
    )
    _patch_client(monkeypatch, handler)

    result = await search_probe.probe_search_provider(
        "kimi",
        {"MOONSHOT_API_KEY": "sk-test"},
    )

    body = seen["body"]
    assert isinstance(body, dict)
    assert seen["host"] == "api.moonshot.cn"
    assert body["model"] == search_probe.DEFAULT_KIMI_MODEL
    assert "temperature" not in body
    assert body["tools"] == [
        {"type": "builtin_function", "function": {"name": "$web_search"}},
    ]
    assert result["success"] is True
    assert result["result_count"] == 1


@pytest.mark.asyncio
async def test_kimi_model_override_reaches_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}
    handler = _kimi_handler(
        httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        ),
        seen,
    )
    _patch_client(monkeypatch, handler)

    await search_probe.probe_search_provider(
        "kimi",
        {
            "MOONSHOT_API_KEY": "sk-test",
            "MOONSHOT_SEARCH_MODEL": "kimi-k3",
        },
    )

    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "kimi-k3"


@pytest.mark.asyncio
async def test_kimi_tool_calls_reply_counts_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``$web_search`` is builtin, so a healthy reply is a ``tool_calls`` turn."""
    seen: dict[str, object] = {}
    handler = _kimi_handler(
        httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "$web_search",
                                        "arguments": "{}",
                                    },
                                },
                            ],
                        },
                        "finish_reason": "tool_calls",
                    },
                ],
            },
        ),
        seen,
    )
    _patch_client(monkeypatch, handler)

    result = await search_probe.probe_search_provider(
        "kimi",
        {"MOONSHOT_API_KEY": "sk-test"},
    )

    assert result["success"] is True
    assert result["result_count"] == 1


@pytest.mark.asyncio
async def test_kimi_unavailable_model_is_explained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retired model must not surface as a bare 404 (#1926)."""
    seen: dict[str, object] = {}
    handler = _kimi_handler(
        httpx.Response(
            404,
            json={
                "error": {
                    "message": "Not found the model moonshot-v1-128k or Permission denied",
                    "type": "resource_not_found_error",
                },
            },
        ),
        seen,
    )
    _patch_client(monkeypatch, handler)

    result = await search_probe.probe_search_provider(
        "kimi",
        {"MOONSHOT_API_KEY": "sk-test"},
    )

    assert result["success"] is False
    assert result["error_type"] == "invalid_config"
    error = result["error"] or ""
    # Points at the knob that fixes it, instead of echoing Moonshot's
    # "Not found ... or Permission denied" ambiguity.
    assert "MOONSHOT_SEARCH_MODEL" in error
    assert search_probe.DEFAULT_KIMI_MODEL in error


@pytest.mark.asyncio
async def test_kimi_auth_error_keeps_its_own_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}
    handler = _kimi_handler(
        httpx.Response(401, json={"error": {"message": "bad key", "type": "invalid_api_key"}}),
        seen,
    )
    _patch_client(monkeypatch, handler)

    result = await search_probe.probe_search_provider(
        "kimi",
        {"MOONSHOT_API_KEY": "bad"},
    )

    assert result["success"] is False
    assert result["error_type"] == "auth_error"


@pytest.mark.asyncio
async def test_kimi_missing_key() -> None:
    result = await search_probe.probe_search_provider("kimi", {})
    assert result["success"] is False
    assert result["error_type"] == "invalid_config"
    assert "MOONSHOT_API_KEY" in (result.get("error") or "")
