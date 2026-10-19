"""Shared token-bucket rate limiter and concurrency semaphore for LLM providers.

Maintains concurrency and rate limit state keyed by (provider_name, api_key_hash)
so that all agents (regular, expert, team members) and background tasks (cron)
sharing credentials are governed by the same limits and backoff policies.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderRateLimitConfig:
    """Configurable rate limiting, concurrency and retry parameters for a provider."""

    requests_per_minute: int | None = None
    max_concurrent_requests: int | None = None
    retry_max_attempts: int | None = None
    retry_base_delay: float | None = None
    retry_max_delay: float | None = None
    retry_jitter: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ProviderRateLimitConfig:
        if not data or not isinstance(data, dict):
            return cls()

        def _to_int(val: Any) -> int | None:
            if val is None:
                return None
            try:
                v = int(val)
                return v if v > 0 else None
            except (TypeError, ValueError):
                return None

        def _to_float(val: Any) -> float | None:
            if val is None:
                return None
            try:
                v = float(val)
                return v if v >= 0 else None
            except (TypeError, ValueError):
                return None

        rpm = _to_int(data.get("requests_per_minute"))
        if rpm is None:
            rpm = _to_int(data.get("rate_limit_rpm"))

        concurrency = _to_int(data.get("max_concurrent_requests"))
        if concurrency is None:
            concurrency = _to_int(data.get("max_concurrency"))

        max_attempts = _to_int(data.get("retry_max_attempts"))
        if max_attempts is None:
            max_attempts = _to_int(data.get("retry_attempts"))

        base_delay = _to_float(data.get("retry_base_delay") or data.get("retry_delay"))
        max_delay = _to_float(data.get("retry_max_delay"))
        jitter = (
            bool(data["retry_jitter"])
            if "retry_jitter" in data and data["retry_jitter"] is not None
            else None
        )

        return cls(
            requests_per_minute=rpm,
            max_concurrent_requests=concurrency,
            retry_max_attempts=max_attempts,
            retry_base_delay=base_delay,
            retry_max_delay=max_delay,
            retry_jitter=jitter,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "requests_per_minute": self.requests_per_minute,
            "max_concurrent_requests": self.max_concurrent_requests,
            "retry_max_attempts": self.retry_max_attempts,
            "retry_base_delay": self.retry_base_delay,
            "retry_max_delay": self.retry_max_delay,
            "retry_jitter": self.retry_jitter,
        }


class RateLimitTimeoutError(RuntimeError):
    """Raised when acquiring a rate limit token or concurrency slot exceeds timeout."""


class TokenBucket:
    """Thread-safe token bucket rate limiter with monotonic refill.

    Refills tokens smoothly over time up to capacity = requests_per_minute.
    Supports both sync acquire (time.sleep) and async aacquire (asyncio.sleep).
    """

    def __init__(
        self,
        requests_per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._capacity = max(1.0, float(requests_per_minute))
        self._rate = self._capacity / 60.0  # tokens per second
        self._tokens = self._capacity
        self._last_refill = self._clock()
        self._sync_lock = threading.Lock()
        self._async_lock = asyncio.Lock()

    @property
    def capacity(self) -> float:
        return self._capacity

    @property
    def refill_rate(self) -> float:
        return self._rate

    def update_rate(self, requests_per_minute: int) -> None:
        """Update bucket parameters while preserving current tokens ratio."""
        with self._sync_lock:
            now = self._clock()
            self._refill(now)
            ratio = self._tokens / self._capacity if self._capacity > 0 else 1.0
            self._capacity = max(1.0, float(requests_per_minute))
            self._rate = self._capacity / 60.0
            self._tokens = min(self._capacity, ratio * self._capacity)
            self._last_refill = now

    def _refill(self, now: float) -> None:
        elapsed = now - self._last_refill
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_refill = now

    def current_tokens(self) -> float:
        with self._sync_lock:
            self._refill(self._clock())
            return self._tokens

    def acquire(self, tokens: float = 1.0, *, timeout: float | None = None) -> bool:
        """Synchronously acquire *tokens*. Sleeps if not enough tokens are available."""
        start = self._clock()
        while True:
            with self._sync_lock:
                now = self._clock()
                self._refill(now)
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                deficit = tokens - self._tokens
                wait_time = deficit / self._rate

            if timeout is not None:
                elapsed = self._clock() - start
                remaining = timeout - elapsed
                if remaining < wait_time:
                    return False

            time.sleep(min(wait_time, 0.1 if timeout is not None else wait_time))

    async def aacquire(self, tokens: float = 1.0, *, timeout: float | None = None) -> bool:
        """Asynchronously acquire *tokens*. Awaits asyncio.sleep if tokens needed."""
        start = self._clock()
        while True:
            async with self._async_lock:
                with self._sync_lock:
                    now = self._clock()
                    self._refill(now)
                    if self._tokens >= tokens:
                        self._tokens -= tokens
                        return True
                    deficit = tokens - self._tokens
                    wait_time = deficit / self._rate

            if timeout is not None:
                elapsed = self._clock() - start
                remaining = timeout - elapsed
                if remaining < wait_time:
                    return False

            sleep_duration = min(wait_time, 0.1 if timeout is not None else wait_time)
            await asyncio.sleep(sleep_duration)


class ConcurrencyLimiter:
    """Bounded concurrency limiter supporting both sync and async callers.

    Tracks active in-flight requests against max_concurrency.
    """

    def __init__(self, max_concurrency: int) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self._max = max_concurrency
        self._current = 0
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._async_sem = asyncio.Semaphore(max_concurrency)

    @property
    def max_concurrency(self) -> int:
        return self._max

    @property
    def current_in_flight(self) -> int:
        with self._lock:
            return self._current

    def update_limit(self, max_concurrency: int) -> None:
        """Update maximum concurrency limit."""
        if max_concurrency < 1:
            return
        with self._cond:
            diff = max_concurrency - self._max
            self._max = max_concurrency
            if diff > 0:
                for _ in range(diff):
                    self._async_sem.release()
                self._cond.notify_all()

    def acquire(self, *, timeout: float | None = None) -> bool:
        """Acquire a concurrency slot synchronously."""
        with self._cond:
            if not self._cond.wait_for(lambda: self._current < self._max, timeout=timeout):
                return False
            self._current += 1
            return True

    def release(self) -> None:
        """Release a concurrency slot synchronously."""
        with self._cond:
            if self._current > 0:
                self._current -= 1
                self._cond.notify()

    async def aacquire(self, *, timeout: float | None = None) -> bool:
        """Acquire a concurrency slot asynchronously."""
        try:
            if timeout is not None:
                await asyncio.wait_for(self._async_sem.acquire(), timeout=timeout)
            else:
                await self._async_sem.acquire()
            with self._lock:
                self._current += 1
            return True
        except TimeoutError:
            return False

    def arelease(self) -> None:
        """Release a concurrency slot asynchronously."""
        with self._lock:
            if self._current > 0:
                self._current -= 1
        self._async_sem.release()

    @contextmanager
    def concurrency(self, *, timeout: float | None = None) -> Iterator[None]:
        if not self.acquire(timeout=timeout):
            raise RateLimitTimeoutError(
                f"Concurrency limit ({self._max}) reached; timed out waiting for available slot"
            )
        try:
            yield
        finally:
            self.release()

    @asynccontextmanager
    async def aconcurrency(self, *, timeout: float | None = None) -> AsyncIterator[None]:
        acquired = await self.aacquire(timeout=timeout)
        if not acquired:
            raise RateLimitTimeoutError(
                f"Concurrency limit ({self._max}) reached; timed out waiting for available slot"
            )
        try:
            yield
        finally:
            self.arelease()


class ProviderLimiter:
    """Bundles rate limiter, concurrency controller, and retry policy for one provider key."""

    def __init__(
        self,
        key: str,
        config: ProviderRateLimitConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.key = key
        self.config = config
        self._clock = clock
        self.token_bucket: TokenBucket | None = (
            TokenBucket(config.requests_per_minute, clock=clock)
            if config.requests_per_minute and config.requests_per_minute > 0
            else None
        )
        self.concurrency_limiter: ConcurrencyLimiter | None = (
            ConcurrencyLimiter(config.max_concurrent_requests)
            if config.max_concurrent_requests and config.max_concurrent_requests > 0
            else None
        )

    def update_config(self, config: ProviderRateLimitConfig) -> None:
        self.config = config
        if config.requests_per_minute and config.requests_per_minute > 0:
            if self.token_bucket is not None:
                self.token_bucket.update_rate(config.requests_per_minute)
            else:
                self.token_bucket = TokenBucket(config.requests_per_minute, clock=self._clock)
        else:
            self.token_bucket = None

        if config.max_concurrent_requests and config.max_concurrent_requests > 0:
            if self.concurrency_limiter is not None:
                self.concurrency_limiter.update_limit(config.max_concurrent_requests)
            else:
                self.concurrency_limiter = ConcurrencyLimiter(config.max_concurrent_requests)
        else:
            self.concurrency_limiter = None

    def acquire(self, *, timeout: float | None = None) -> None:
        """Acquire rate limiter token and concurrency slot synchronously."""
        if self.token_bucket is not None and not self.token_bucket.acquire(timeout=timeout):
            raise RateLimitTimeoutError(
                f"Rate limit for {self.key} exceeded; acquire timed out after {timeout}s"
            )
        if self.concurrency_limiter is not None and not self.concurrency_limiter.acquire(
            timeout=timeout
        ):
            raise RateLimitTimeoutError(
                f"Concurrency limit ({self.concurrency_limiter.max_concurrency}) for {self.key} reached"
            )

    def release_concurrency(self) -> None:
        """Release concurrency slot if concurrency limiter is active."""
        if self.concurrency_limiter is not None:
            self.concurrency_limiter.release()

    async def aacquire(self, *, timeout: float | None = None) -> None:
        """Acquire rate limiter token and concurrency slot asynchronously."""
        if self.token_bucket is not None:
            acquired = await self.token_bucket.aacquire(timeout=timeout)
            if not acquired:
                raise RateLimitTimeoutError(
                    f"Rate limit for {self.key} exceeded; aacquire timed out after {timeout}s"
                )
        if self.concurrency_limiter is not None:
            acquired = await self.concurrency_limiter.aacquire(timeout=timeout)
            if not acquired:
                raise RateLimitTimeoutError(
                    f"Concurrency limit ({self.concurrency_limiter.max_concurrency}) for {self.key} reached"
                )

    def arelease_concurrency(self) -> None:
        """Release concurrency slot if concurrency limiter is active asynchronously."""
        if self.concurrency_limiter is not None:
            self.concurrency_limiter.arelease()

    @contextmanager
    def limit(self, *, timeout: float | None = None) -> Iterator[None]:
        self.acquire(timeout=timeout)
        try:
            yield
        finally:
            self.release_concurrency()

    @asynccontextmanager
    async def alimit(self, *, timeout: float | None = None) -> AsyncIterator[None]:
        await self.aacquire(timeout=timeout)
        try:
            yield
        finally:
            self.arelease_concurrency()


def make_limiter_key(provider_name: str, api_key: str | None = None) -> str:
    """Create a stable key for grouping limiters by provider and credential."""
    prov = (provider_name or "").strip().lower()
    if not api_key or not api_key.strip():
        return f"{prov}:default"
    hashed = hashlib.sha256(api_key.strip().encode("utf-8")).hexdigest()[:16]
    return f"{prov}:{hashed}"


class RateLimitRegistry:
    """Process-wide registry mapping provider keys to shared rate and concurrency limiters."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._limiters: dict[str, ProviderLimiter] = {}

    def configure(self, key: str, config: ProviderRateLimitConfig) -> ProviderLimiter:
        with self._lock:
            limiter = self._limiters.get(key)
            if limiter is not None:
                limiter.update_config(config)
            else:
                limiter = ProviderLimiter(key, config, clock=self._clock)
                self._limiters[key] = limiter
            return limiter

    def get(
        self,
        key: str,
        default_config: ProviderRateLimitConfig | None = None,
    ) -> ProviderLimiter:
        with self._lock:
            limiter = self._limiters.get(key)
            if limiter is None:
                cfg = default_config or ProviderRateLimitConfig()
                limiter = ProviderLimiter(key, cfg, clock=self._clock)
                self._limiters[key] = limiter
            return limiter

    def get_by_provider(
        self,
        provider_name: str,
        api_key: str | None = None,
        default_config: ProviderRateLimitConfig | None = None,
    ) -> ProviderLimiter:
        key = make_limiter_key(provider_name, api_key)
        return self.get(key, default_config=default_config)

    def reset(self) -> None:
        """Clear all active limiters (primarily for testing)."""
        with self._lock:
            self._limiters.clear()


RATE_LIMIT_REGISTRY = RateLimitRegistry()

__all__ = [
    "ConcurrencyLimiter",
    "ProviderLimiter",
    "ProviderRateLimitConfig",
    "RATE_LIMIT_REGISTRY",
    "RateLimitRegistry",
    "RateLimitTimeoutError",
    "TokenBucket",
    "make_limiter_key",
]
