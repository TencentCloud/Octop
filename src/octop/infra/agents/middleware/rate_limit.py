"""Middleware enforcing shared rate limits, concurrency control, and backoff retries."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage
from langgraph.errors import GraphBubbleUp

from octop.i18n.domains.stream import model_retry_failure_prompt
from octop.infra.agents.providers.backoff import (
    calculate_backoff_delay,
    extract_retry_after,
    is_retryable_provider_error,
    is_transient_rate_limit,
)
from octop.infra.agents.providers.rate_limiter import (
    RATE_LIMIT_REGISTRY,
    ProviderLimiter,
    RateLimitRegistry,
    make_limiter_key,
)

logger = logging.getLogger(__name__)


def _extract_model_ref(request: ModelRequest[Any]) -> str:
    configurable = getattr(request, "runtime", None)
    config = getattr(configurable, "config", None)
    if isinstance(config, dict):
        cfg = config.get("configurable")
        if isinstance(cfg, dict) and isinstance(cfg.get("model"), str):
            return cfg["model"].strip()
    # Check model attributes
    model = getattr(request, "model", None)
    if model is not None:
        ref = getattr(model, "model", None)
        if isinstance(ref, str) and ref:
            return ref.strip()
    return ""


class ProviderRateLimitRetryMiddleware(AgentMiddleware[Any, Any]):
    """AgentMiddleware enforcing token bucket, concurrency throttle, and jittered backoff."""

    def __init__(
        self,
        *,
        registry: RateLimitRegistry | None = None,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        on_failure: Callable[[Exception], str] | Literal["error"] | None = None,
        key_resolver: Callable[[ModelRequest[Any]], str] | None = None,
    ) -> None:
        super().__init__()
        self._registry = registry or RATE_LIMIT_REGISTRY
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.on_failure = on_failure
        self._key_resolver = key_resolver

    def _resolve_limiter(self, request: ModelRequest[Any]) -> ProviderLimiter:
        if self._key_resolver is not None:
            key = self._key_resolver(request)
            if key:
                return self._registry.get(key)

        ref = _extract_model_ref(request)
        provider = ref.partition("/")[0] if "/" in ref else ref
        key = make_limiter_key(provider)
        return self._registry.get(key)

    def _handle_failure(self, exc: Exception) -> ModelResponse[Any]:
        if self.on_failure == "error":
            raise exc
        content = (
            self.on_failure(exc)
            if callable(self.on_failure)
            else model_retry_failure_prompt(exc, "en")
        )
        return ModelResponse(result=[AIMessage(content=content)])

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        limiter = self._resolve_limiter(request)
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            limiter.acquire()
            try:
                return handler(request)
            except GraphBubbleUp:
                raise
            except Exception as exc:
                last_error = exc
                if not is_retryable_provider_error(exc) or attempt >= self.max_retries:
                    raise
                retry_after = extract_retry_after(exc) if is_transient_rate_limit(exc) else None
                delay = calculate_backoff_delay(
                    attempt,
                    base_delay=self.initial_delay,
                    max_delay=self.max_delay,
                    retry_after=retry_after,
                    jitter=self.jitter,
                )
                logger.warning(
                    "Model call transient error (attempt %d/%d), retrying in %.2fs: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    delay,
                    exc,
                )
                if delay > 0:
                    time.sleep(delay)
            finally:
                limiter.release_concurrency()

        return self._handle_failure(last_error or RuntimeError("retry loop exhausted"))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        limiter = self._resolve_limiter(request)
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            await limiter.aacquire()
            try:
                return await handler(request)
            except GraphBubbleUp:
                raise
            except Exception as exc:
                last_error = exc
                if not is_retryable_provider_error(exc) or attempt >= self.max_retries:
                    raise
                retry_after = extract_retry_after(exc) if is_transient_rate_limit(exc) else None
                delay = calculate_backoff_delay(
                    attempt,
                    base_delay=self.initial_delay,
                    max_delay=self.max_delay,
                    retry_after=retry_after,
                    jitter=self.jitter,
                )
                logger.warning(
                    "Model call transient error (attempt %d/%d), retrying in %.2fs: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    delay,
                    exc,
                )
                if delay > 0:
                    await asyncio.sleep(delay)
            finally:
                limiter.arelease_concurrency()

        return self._handle_failure(last_error or RuntimeError("retry loop exhausted"))


__all__ = ["ProviderRateLimitRetryMiddleware"]
