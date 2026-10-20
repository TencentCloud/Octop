"""Unit tests for ProviderRateLimitRetryMiddleware and concurrency throttling."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

from octop.infra.agents.middleware import rate_limit
from octop.infra.agents.middleware.rate_limit import ProviderRateLimitRetryMiddleware
from octop.infra.agents.providers.rate_limiter import (
    ProviderRateLimitConfig,
    RateLimitRegistry,
    make_limiter_key,
)


def _mock_request(model_ref: str = "glm/glm-5.3") -> ModelRequest:
    model = SimpleNamespace(model=model_ref)
    return ModelRequest(model=model, messages=[HumanMessage(content="hi")])


def test_rate_limit_middleware_retries_on_429() -> None:
    registry = RateLimitRegistry()
    key = make_limiter_key("glm")
    registry.configure(key, ProviderRateLimitConfig(requests_per_minute=60, retry_max_attempts=3))

    middleware = ProviderRateLimitRetryMiddleware(
        registry=registry,
        max_retries=3,
        initial_delay=0,
        max_delay=0,
        jitter=False,
    )

    attempts = 0

    def handler(req: ModelRequest) -> ModelResponse:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("HTTP 429 too many requests")
        return ModelResponse(result=[AIMessage(content="success")])

    resp = middleware.wrap_model_call(_mock_request(), handler)
    assert resp.result[0].content == "success"
    assert attempts == 3


@pytest.mark.asyncio
async def test_rate_limit_middleware_async_retries_on_glm_1302() -> None:
    registry = RateLimitRegistry()
    key = make_limiter_key("glm")
    registry.configure(key, ProviderRateLimitConfig(requests_per_minute=60, retry_max_attempts=3))

    middleware = ProviderRateLimitRetryMiddleware(
        registry=registry,
        max_retries=3,
        initial_delay=0,
        max_delay=0,
        jitter=False,
    )

    attempts = 0

    async def handler(req: ModelRequest) -> ModelResponse:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise RuntimeError("Error code: 1302 - {'error': {'message': '系统繁忙，请稍后再试'}}")
        return ModelResponse(result=[AIMessage(content="glm success")])

    resp = await middleware.awrap_model_call(_mock_request(), handler)
    assert resp.result[0].content == "glm success"
    assert attempts == 2


def test_rate_limit_middleware_releases_concurrency_before_retry_sleep(monkeypatch) -> None:
    registry = RateLimitRegistry()
    key = make_limiter_key("glm")
    limiter = registry.configure(key, ProviderRateLimitConfig(max_concurrent_requests=1))
    middleware = ProviderRateLimitRetryMiddleware(
        registry=registry,
        max_retries=1,
        initial_delay=1,
        max_delay=1,
        jitter=False,
    )
    in_flight_during_sleep: list[int] = []
    attempts = 0

    def fake_sleep(_delay: float) -> None:
        in_flight_during_sleep.append(limiter.concurrency_limiter.current_in_flight)

    def handler(_request: ModelRequest) -> ModelResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("HTTP 429 too many requests")
        return ModelResponse(result=[AIMessage(content="success")])

    monkeypatch.setattr(rate_limit.time, "sleep", fake_sleep)

    response = middleware.wrap_model_call(_mock_request(), handler)

    assert response.result[0].content == "success"
    assert in_flight_during_sleep == [0]


@pytest.mark.asyncio
async def test_rate_limit_middleware_async_releases_concurrency_before_retry_sleep(
    monkeypatch,
) -> None:
    registry = RateLimitRegistry()
    key = make_limiter_key("glm")
    limiter = registry.configure(key, ProviderRateLimitConfig(max_concurrent_requests=1))
    middleware = ProviderRateLimitRetryMiddleware(
        registry=registry,
        max_retries=1,
        initial_delay=1,
        max_delay=1,
        jitter=False,
    )
    in_flight_during_sleep: list[int] = []
    attempts = 0

    async def fake_sleep(_delay: float) -> None:
        in_flight_during_sleep.append(limiter.concurrency_limiter.current_in_flight)

    async def handler(_request: ModelRequest) -> ModelResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("HTTP 429 too many requests")
        return ModelResponse(result=[AIMessage(content="success")])

    monkeypatch.setattr(rate_limit.asyncio, "sleep", fake_sleep)

    response = await middleware.awrap_model_call(_mock_request(), handler)

    assert response.result[0].content == "success"
    assert in_flight_during_sleep == [0]


def test_rate_limit_middleware_does_not_retry_auth_error() -> None:
    registry = RateLimitRegistry()
    middleware = ProviderRateLimitRetryMiddleware(
        registry=registry,
        max_retries=3,
        initial_delay=0,
        max_delay=0,
    )

    attempts = 0

    def handler(req: ModelRequest) -> ModelResponse:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("Error code: 401 - Incorrect API key provided")

    with pytest.raises(RuntimeError) as caught:
        middleware.wrap_model_call(_mock_request(), handler)

    assert "401" in str(caught.value)
    # Must fail on the very first attempt without wasting retries!
    assert attempts == 1


def test_rate_limit_middleware_releases_concurrency_on_failure() -> None:
    registry = RateLimitRegistry()
    key = make_limiter_key("glm")
    registry.configure(key, ProviderRateLimitConfig(max_concurrent_requests=1))

    middleware = ProviderRateLimitRetryMiddleware(
        registry=registry,
        max_retries=1,
        initial_delay=0,
        max_delay=0,
    )

    def fail_handler(req: ModelRequest) -> ModelResponse:
        raise ValueError("unhandled fatal crash")

    with pytest.raises(ValueError):
        middleware.wrap_model_call(_mock_request(), fail_handler)

    # Concurrency limiter must be free
    limiter = registry.get(key)
    assert limiter.concurrency_limiter.current_in_flight == 0

    # Next call should succeed without blocking
    ok_handler = MagicMock(return_value=ModelResponse(result=[AIMessage(content="ok")]))
    resp = middleware.wrap_model_call(_mock_request(), ok_handler)
    assert resp.result[0].content == "ok"
    assert limiter.concurrency_limiter.current_in_flight == 0


@pytest.mark.asyncio
async def test_multi_agent_shared_concurrency_throttle() -> None:
    registry = RateLimitRegistry()
    key = make_limiter_key("glm")
    registry.configure(
        key,
        ProviderRateLimitConfig(max_concurrent_requests=2, retry_max_attempts=0),
    )

    middleware = ProviderRateLimitRetryMiddleware(
        registry=registry,
        max_retries=0,
    )

    limiter = registry.get(key)
    max_observed_concurrency = 0

    async def agent_task() -> None:
        nonlocal max_observed_concurrency

        async def handler(req: ModelRequest) -> ModelResponse:
            nonlocal max_observed_concurrency
            current = limiter.concurrency_limiter.current_in_flight
            if current > max_observed_concurrency:
                max_observed_concurrency = current
            await asyncio.sleep(0.05)
            return ModelResponse(result=[AIMessage(content="done")])

        await middleware.awrap_model_call(_mock_request(), handler)

    # Launch 5 concurrent agent tasks sharing the same provider key
    await asyncio.gather(
        agent_task(),
        agent_task(),
        agent_task(),
        agent_task(),
        agent_task(),
    )

    # At no point should concurrent in-flight requests have exceeded 2
    assert max_observed_concurrency <= 2
    assert limiter.concurrency_limiter.current_in_flight == 0
