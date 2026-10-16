from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

from octop.infra.agents.middleware import model_failover
from octop.infra.agents.middleware.model_failover import (
    AutoRouteCandidate,
    SafeModelFailoverMiddleware,
)
from octop.infra.agents.providers.health import ModelHealthRegistry


def _model(ref: str, cap: int) -> SimpleNamespace:
    provider, _, model = ref.partition("/")
    return SimpleNamespace(
        model=ref,
        provider=provider,
        model_name=model,
        profile={"max_input_tokens": cap},
    )


@pytest.mark.asyncio
async def test_auto_route_switches_after_retry_exhaustion(monkeypatch) -> None:
    models = {"p/a": _model("p/a", 100_000), "p/b": _model("p/b", 100_000)}
    configurable = {"model": "p/a", "octop_auto_route": True}
    health = ModelHealthRegistry(clock=lambda: 100.0)
    middleware = SafeModelFailoverMiddleware(
        health=health,
        candidates=lambda _current, _vision: [AutoRouteCandidate("p/b", 100_000)],
        model_for_ref=models.__getitem__,
        max_retries=1,
        initial_delay=0,
        max_delay=0,
        on_failure="error",
    )
    monkeypatch.setattr(
        model_failover,
        "_configurable",
        lambda _request: configurable,
    )
    attempts: list[tuple[str, str]] = []

    async def handler(request: ModelRequest) -> ModelResponse:
        attempts.append((request.model.model, configurable["model"]))
        if request.model.model == "p/a":
            raise RuntimeError("HTTP 503 service unavailable")
        return ModelResponse(result=[AIMessage(content="ok")])

    response = await middleware.awrap_model_call(
        ModelRequest(model=models["p/a"], messages=[HumanMessage(content="hello")]),
        handler,
    )

    assert response.result[0].content == "ok"
    assert attempts == [("p/a", "p/a"), ("p/a", "p/a"), ("p/b", "p/b")]
    assert configurable["model"] == "p/b"
    assert not health.is_routable("p/a")


@pytest.mark.parametrize("automatic", [False, True])
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.asyncio
async def test_error_policy_raises_after_all_routes_exhaust_retries(
    monkeypatch, automatic: bool, asynchronous: bool
) -> None:
    models = {"p/a": _model("p/a", 100_000), "p/b": _model("p/b", 100_000)}
    configurable = {"model": "p/a", "octop_auto_route": automatic}
    health = ModelHealthRegistry(clock=lambda: 100.0)
    middleware = SafeModelFailoverMiddleware(
        health=health,
        candidates=lambda _current, _vision: [AutoRouteCandidate("p/b", 100_000)],
        model_for_ref=models.__getitem__,
        max_retries=1,
        initial_delay=0,
        max_delay=0,
        on_failure="error",
    )
    monkeypatch.setattr(model_failover, "_configurable", lambda _request: configurable)
    error = RuntimeError("HTTP 503 service unavailable")
    handler = AsyncMock(side_effect=error) if asynchronous else MagicMock(side_effect=error)
    request = ModelRequest(model=models["p/a"], messages=[HumanMessage(content="hello")])

    with pytest.raises(RuntimeError) as caught:
        if asynchronous:
            await middleware.awrap_model_call(request, handler)
        else:
            middleware.wrap_model_call(request, handler)

    assert caught.value is error
    assert [call.args[0].model.model for call in handler.call_args_list] == (
        ["p/a", "p/a", "p/b", "p/b"] if automatic else ["p/a", "p/a"]
    )
    assert not health.is_routable("p/a")
    if automatic:
        assert not health.is_routable("p/b")


@pytest.mark.asyncio
async def test_explicit_route_retries_but_does_not_switch(monkeypatch) -> None:
    models = {"p/a": _model("p/a", 100_000), "p/b": _model("p/b", 100_000)}
    health = ModelHealthRegistry(clock=lambda: 100.0)
    middleware = SafeModelFailoverMiddleware(
        health=health,
        candidates=lambda _current, _vision: [AutoRouteCandidate("p/b", 100_000)],
        model_for_ref=models.__getitem__,
        max_retries=1,
        initial_delay=0,
        max_delay=0,
    )
    monkeypatch.setattr(
        model_failover,
        "_configurable",
        lambda _request: {"model": "p/a", "octop_auto_route": False},
    )
    handler = MagicMock(side_effect=RuntimeError("HTTP 503 service unavailable"))

    response = middleware.wrap_model_call(
        ModelRequest(model=models["p/a"], messages=[HumanMessage(content="hello")]),
        handler,
    )

    assert "[model_call_failed]" in str(response.result[0].content)
    assert handler.call_count == 2
    assert not health.is_routable("p/a")


def test_terminal_failure_uses_observability_callback(monkeypatch) -> None:
    model = _model("p/a", 100_000)
    on_failure = MagicMock(return_value="tracked failure")
    middleware = SafeModelFailoverMiddleware(
        health=ModelHealthRegistry(clock=lambda: 100.0),
        candidates=lambda _current, _vision: [],
        model_for_ref=lambda _ref: model,
        max_retries=0,
        initial_delay=0,
        max_delay=0,
        on_failure=on_failure,
    )
    monkeypatch.setattr(
        model_failover,
        "_configurable",
        lambda _request: {"model": "p/a", "octop_auto_route": False},
    )
    error = RuntimeError("HTTP 503 service unavailable")

    response = middleware.wrap_model_call(
        ModelRequest(model=model, messages=[HumanMessage(content="hello")]),
        MagicMock(side_effect=error),
    )

    assert response.result[0].content == "tracked failure"
    on_failure.assert_called_once_with(error)


@pytest.mark.asyncio
async def test_failover_skips_model_with_smaller_context(monkeypatch) -> None:
    models = {
        "p/a": _model("p/a", 100_000),
        "p/small": _model("p/small", 1_000),
        "p/large": _model("p/large", 100_000),
    }
    middleware = SafeModelFailoverMiddleware(
        health=ModelHealthRegistry(clock=lambda: 100.0),
        candidates=lambda _current, _vision: [
            AutoRouteCandidate("p/small", 1_000),
            AutoRouteCandidate("p/large", 100_000),
        ],
        model_for_ref=models.__getitem__,
        max_retries=0,
        initial_delay=0,
        max_delay=0,
    )
    monkeypatch.setattr(
        model_failover,
        "_configurable",
        lambda _request: {"model": "p/a", "octop_auto_route": True},
    )
    monkeypatch.setattr(model_failover, "_estimated_input_tokens", lambda _request: 2_000)
    attempts: list[str] = []

    async def handler(request: ModelRequest) -> ModelResponse:
        attempts.append(request.model.model)
        if request.model.model == "p/a":
            raise RuntimeError("context_length_exceeded")
        return ModelResponse(result=[AIMessage(content="ok")])

    response = await middleware.awrap_model_call(
        ModelRequest(model=models["p/a"], messages=[HumanMessage(content="hello")]),
        handler,
    )

    assert response.result[0].content == "ok"
    assert attempts == ["p/a", "p/large"]


@pytest.mark.asyncio
async def test_failover_respects_agent_context_cap(monkeypatch) -> None:
    models = {"p/a": _model("p/a", 100_000), "p/b": _model("p/b", 100_000)}
    middleware = SafeModelFailoverMiddleware(
        health=ModelHealthRegistry(clock=lambda: 100.0),
        candidates=lambda _current, _vision: [AutoRouteCandidate("p/b", 100_000)],
        model_for_ref=models.__getitem__,
        max_retries=0,
        initial_delay=0,
        max_delay=0,
    )
    monkeypatch.setattr(
        model_failover,
        "_configurable",
        lambda _request: {
            "model": "p/a",
            "octop_auto_route": True,
            "max_input_tokens": 1_000,
        },
    )
    monkeypatch.setattr(model_failover, "_estimated_input_tokens", lambda _request: 2_000)
    attempts: list[str] = []

    async def handler(request: ModelRequest) -> ModelResponse:
        attempts.append(request.model.model)
        raise RuntimeError("context_length_exceeded")

    response = await middleware.awrap_model_call(
        ModelRequest(model=models["p/a"], messages=[HumanMessage(content="hello")]),
        handler,
    )

    assert "[model_call_failed]" in str(response.result[0].content)
    assert attempts == ["p/a"]


@pytest.mark.asyncio
async def test_failover_does_not_retry_unknown_invalid_request(monkeypatch) -> None:
    model = _model("p/a", 100_000)
    middleware = SafeModelFailoverMiddleware(
        health=ModelHealthRegistry(clock=lambda: 100.0),
        candidates=lambda _current, _vision: [AutoRouteCandidate("p/b", 100_000)],
        model_for_ref=lambda _ref: _model("p/b", 100_000),
        max_retries=0,
        initial_delay=0,
        max_delay=0,
    )
    monkeypatch.setattr(
        model_failover,
        "_configurable",
        lambda _request: {"model": "p/a", "octop_auto_route": True},
    )
    handler = MagicMock(side_effect=RuntimeError("HTTP 400 invalid tool schema"))

    response = await middleware.awrap_model_call(
        ModelRequest(model=model, messages=[HumanMessage(content="hello")]),
        handler,
    )

    assert "[model_call_failed]" in str(response.result[0].content)
    assert handler.call_count == 1


@pytest.mark.asyncio
async def test_provider_failure_skips_sibling_model(monkeypatch) -> None:
    models = {
        "p/a": _model("p/a", 100_000),
        "p/b": _model("p/b", 100_000),
        "q/c": _model("q/c", 100_000),
    }
    configurable = {"model": "p/a", "octop_auto_route": True}
    middleware = SafeModelFailoverMiddleware(
        health=ModelHealthRegistry(clock=lambda: 100.0),
        candidates=lambda _current, _vision: [
            AutoRouteCandidate("p/b", 100_000),
            AutoRouteCandidate("q/c", 100_000),
        ],
        model_for_ref=models.__getitem__,
        max_retries=0,
        initial_delay=0,
        max_delay=0,
    )
    monkeypatch.setattr(model_failover, "_configurable", lambda _request: configurable)
    attempts: list[str] = []

    async def handler(request: ModelRequest) -> ModelResponse:
        attempts.append(request.model.model)
        if request.model.model == "p/a":
            raise RuntimeError("HTTP 429 too many requests")
        return ModelResponse(result=[AIMessage(content="ok")])

    response = await middleware.awrap_model_call(
        ModelRequest(model=models["p/a"], messages=[HumanMessage(content="hello")]),
        handler,
    )

    assert response.result[0].content == "ok"
    assert attempts == ["p/a", "q/c"]
    assert configurable["model"] == "q/c"
