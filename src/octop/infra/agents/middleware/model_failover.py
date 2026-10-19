"""Health-aware and context-safe model failover for AUTO-routed turns."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Literal, cast

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.model_retry import ModelRetryMiddleware
from langchain_core.messages import AIMessage
from langgraph.errors import GraphBubbleUp
from octop_harness.context_usage import breakdown_from_model_request
from octop_harness.middleware.runtime import runtime_config
from octop_harness.middleware.turn_model import latest_human_needs_multimodal

from octop.i18n.domains.stream import model_retry_failure_prompt
from octop.infra.agents.providers.backoff import (
    calculate_backoff_delay,
    extract_retry_after,
    is_retryable_provider_error,
    is_transient_rate_limit,
)
from octop.infra.agents.providers.health import (
    FailureScope,
    ModelHealthRegistry,
    classify_model_failure,
)
from octop.infra.agents.providers.rate_limiter import (
    RATE_LIMIT_REGISTRY,
    ProviderLimiter,
    RateLimitRegistry,
    make_limiter_key,
)
from octop.infra.agents.providers.store import AutoRouteCandidate
from octop.infra.agents.settings.runtime_limits import CONFIGURABLE_MAX_INPUT_TOKENS

logger = logging.getLogger(__name__)

AUTO_ROUTE_CONFIG_KEY = "octop_auto_route"
_CONTEXT_SAFETY_RATIO = 0.9


def _configurable(request: ModelRequest[Any]) -> dict[str, Any]:
    config = runtime_config(request)
    configurable = config.get("configurable") if isinstance(config, dict) else None
    return configurable if isinstance(configurable, dict) else {}


def _estimated_input_tokens(request: ModelRequest[Any]) -> int:
    return sum(breakdown_from_model_request(request).values())


def _fits_context(
    candidate: AutoRouteCandidate,
    estimated_tokens: int,
    route_cap: int | None = None,
) -> bool:
    cap = candidate.max_input_tokens
    if route_cap is not None and route_cap > 0:
        cap = min(cap, route_cap) if cap > 0 else route_cap
    if cap <= 0:
        return True
    return estimated_tokens <= int(cap * _CONTEXT_SAFETY_RATIO)


class SafeModelFailoverMiddleware(AgentMiddleware[Any, Any]):
    """Retry one model, then switch only for AUTO and safe failure classes."""

    def __init__(
        self,
        *,
        health: ModelHealthRegistry,
        candidates: Callable[[str, bool], Sequence[AutoRouteCandidate]],
        model_for_ref: Callable[[str], Any],
        max_retries: int,
        initial_delay: float,
        max_delay: float,
        on_failure: Callable[[Exception], str] | Literal["error"] | None = None,
        rate_limit_registry: RateLimitRegistry | None = None,
        limiter_key_resolver: Callable[[str], str] | None = None,
    ) -> None:
        super().__init__()
        self._health = health
        self._candidates = candidates
        self._model_for_ref = model_for_ref
        self._on_failure = on_failure
        self._max_retries = max_retries
        self.max_retries = max_retries
        self._initial_delay = initial_delay
        self.initial_delay = initial_delay
        self._max_delay = max_delay
        self.max_delay = max_delay
        self._rate_limit_registry = rate_limit_registry or RATE_LIMIT_REGISTRY
        self._limiter_key_resolver = limiter_key_resolver
        self._retry = ModelRetryMiddleware(
            max_retries=max_retries,
            initial_delay=initial_delay,
            max_delay=max_delay,
            on_failure="error",
        )

    def _limiter_for_ref(self, ref: str) -> ProviderLimiter:
        if self._limiter_key_resolver is not None:
            key = self._limiter_key_resolver(ref)
            if key:
                return self._rate_limit_registry.get(key)
        provider = ref.partition("/")[0] if "/" in ref else ref
        key = make_limiter_key(provider)
        return self._rate_limit_registry.get(key)

    def _execute_candidate(
        self,
        ref: str,
        routed: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        limiter = self._limiter_for_ref(ref)
        retries = (
            limiter.config.retry_max_attempts
            if limiter.config.retry_max_attempts is not None
            else self._max_retries
        )
        base_delay = (
            limiter.config.retry_base_delay
            if limiter.config.retry_base_delay is not None
            else self._initial_delay
        )
        max_delay = (
            limiter.config.retry_max_delay
            if limiter.config.retry_max_delay is not None
            else self._max_delay
        )
        jitter = (
            limiter.config.retry_jitter
            if limiter.config.retry_jitter is not None
            else (base_delay > 0 and max_delay > 0)
        )

        for attempt in range(retries + 1):
            limiter.acquire()
            try:
                return handler(routed)
            except GraphBubbleUp:
                raise
            except Exception as exc:
                if not is_retryable_provider_error(exc) or attempt >= retries:
                    raise
                retry_after = extract_retry_after(exc) if is_transient_rate_limit(exc) else None
                delay = calculate_backoff_delay(
                    attempt,
                    base_delay=base_delay,
                    max_delay=max_delay,
                    retry_after=retry_after,
                    jitter=jitter,
                )
                logger.warning(
                    "Model %s call transient error (attempt %d/%d), retrying in %.2fs: %s",
                    ref,
                    attempt + 1,
                    retries + 1,
                    delay,
                    exc,
                )
                if delay > 0:
                    time.sleep(delay)
            finally:
                limiter.release_concurrency()

        raise RuntimeError("retry loop exhausted")

    async def _aexecute_candidate(
        self,
        ref: str,
        routed: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        limiter = self._limiter_for_ref(ref)
        retries = (
            limiter.config.retry_max_attempts
            if limiter.config.retry_max_attempts is not None
            else self._max_retries
        )
        base_delay = (
            limiter.config.retry_base_delay
            if limiter.config.retry_base_delay is not None
            else self._initial_delay
        )
        max_delay = (
            limiter.config.retry_max_delay
            if limiter.config.retry_max_delay is not None
            else self._max_delay
        )
        jitter = (
            limiter.config.retry_jitter
            if limiter.config.retry_jitter is not None
            else (base_delay > 0 and max_delay > 0)
        )

        for attempt in range(retries + 1):
            await limiter.aacquire()
            try:
                return await handler(routed)
            except GraphBubbleUp:
                raise
            except Exception as exc:
                if not is_retryable_provider_error(exc) or attempt >= retries:
                    raise
                retry_after = extract_retry_after(exc) if is_transient_rate_limit(exc) else None
                delay = calculate_backoff_delay(
                    attempt,
                    base_delay=base_delay,
                    max_delay=max_delay,
                    retry_after=retry_after,
                    jitter=jitter,
                )
                logger.warning(
                    "Model %s call transient error (attempt %d/%d), retrying in %.2fs: %s",
                    ref,
                    attempt + 1,
                    retries + 1,
                    delay,
                    exc,
                )
                if delay > 0:
                    await asyncio.sleep(delay)
            finally:
                limiter.arelease_concurrency()

        raise RuntimeError("retry loop exhausted")

    def _failure_response(self, exc: Exception) -> ModelResponse[Any]:
        if self._on_failure == "error":
            raise exc
        content = (
            self._on_failure(exc)
            if self._on_failure is not None
            else model_retry_failure_prompt(exc, "en")
        )
        return ModelResponse(result=[AIMessage(content=content)])

    def _route(self, request: ModelRequest[Any]) -> tuple[str, bool]:
        configurable = _configurable(request)
        ref = configurable.get("model")
        return (
            ref.strip() if isinstance(ref, str) else "",
            configurable.get(AUTO_ROUTE_CONFIG_KEY) is True,
        )

    def _fallbacks(self, request: ModelRequest[Any], current_ref: str) -> list[AutoRouteCandidate]:
        needs_multimodal = latest_human_needs_multimodal(list(request.messages or []))
        estimated = _estimated_input_tokens(request)
        raw_route_cap = _configurable(request).get(CONFIGURABLE_MAX_INPUT_TOKENS)
        route_cap = raw_route_cap if isinstance(raw_route_cap, int) else None
        return [
            candidate
            for candidate in self._candidates(current_ref, needs_multimodal)
            if candidate.ref != current_ref
            and self._health.is_routable(candidate.ref)
            and _fits_context(candidate, estimated, route_cap)
        ]

    def _record_failure(self, ref: str, exc: Exception) -> bool:
        decision = classify_model_failure(exc)
        if decision.scope is not FailureScope.NONE:
            self._health.record_failure(ref, kind=decision.kind, scope=decision.scope)
        return decision.failover

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        current_ref, automatic = self._route(request)
        last_error: Exception | None = None
        attempts: list[tuple[str, Any]] = []
        if not automatic or not current_ref or self._health.begin_attempt(current_ref):
            attempts.append((current_ref, request.model))
        if automatic and current_ref:
            attempts.extend(
                (candidate.ref, self._model_for_ref(candidate.ref))
                for candidate in self._fallbacks(request, current_ref)
            )

        for ref, model in attempts:
            if automatic and ref != current_ref and not self._health.begin_attempt(ref):
                continue
            routed = request if model is request.model else request.override(model=model)
            if automatic and ref and ref != current_ref:
                _configurable(request)["model"] = ref
            try:
                response = self._execute_candidate(ref, routed, handler)
            except GraphBubbleUp:
                raise
            except Exception as exc:
                last_error = exc
                may_failover = self._record_failure(ref, exc)
                if not automatic or not may_failover:
                    return self._failure_response(exc)
                logger.warning("AUTO model route failed; trying next candidate: model=%s", ref)
                continue
            self._health.record_success(ref)
            return cast(ModelResponse[Any], response)

        return self._failure_response(
            last_error or RuntimeError("no healthy AUTO model is available")
        )

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        current_ref, automatic = self._route(request)
        last_error: Exception | None = None
        attempts: list[tuple[str, Any]] = []
        if not automatic or not current_ref or self._health.begin_attempt(current_ref):
            attempts.append((current_ref, request.model))
        if automatic and current_ref:
            attempts.extend(
                (candidate.ref, self._model_for_ref(candidate.ref))
                for candidate in self._fallbacks(request, current_ref)
            )

        for ref, model in attempts:
            if automatic and ref != current_ref and not self._health.begin_attempt(ref):
                continue
            routed = request if model is request.model else request.override(model=model)
            if automatic and ref and ref != current_ref:
                _configurable(request)["model"] = ref
            try:
                response = await self._aexecute_candidate(ref, routed, handler)
            except GraphBubbleUp:
                raise
            except Exception as exc:
                last_error = exc
                may_failover = self._record_failure(ref, exc)
                if not automatic or not may_failover:
                    return self._failure_response(exc)
                logger.warning("AUTO model route failed; trying next candidate: model=%s", ref)
                continue
            self._health.record_success(ref)
            return cast(ModelResponse[Any], response)

        return self._failure_response(
            last_error or RuntimeError("no healthy AUTO model is available")
        )


__all__ = [
    "AUTO_ROUTE_CONFIG_KEY",
    "AutoRouteCandidate",
    "SafeModelFailoverMiddleware",
]
