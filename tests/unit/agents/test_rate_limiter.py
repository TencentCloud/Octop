"""Unit tests for token-bucket rate limiter, concurrency controller, and registry."""

from __future__ import annotations

import asyncio

import pytest

from octop.infra.agents.providers.rate_limiter import (
    ConcurrencyLimiter,
    ProviderRateLimitConfig,
    RateLimitRegistry,
    TokenBucket,
    make_limiter_key,
)


def test_token_bucket_initial_and_capacity() -> None:
    current_time = 1000.0

    def clock() -> float:
        return current_time

    bucket = TokenBucket(requests_per_minute=60, clock=clock)

    assert bucket.capacity == 60.0
    assert bucket.refill_rate == 1.0  # 60 tokens / 60 seconds = 1 token/s
    assert bucket.current_tokens() == 60.0


def test_token_bucket_refills_over_time() -> None:
    current_time = 1000.0

    def clock() -> float:
        return current_time

    bucket = TokenBucket(requests_per_minute=60, clock=clock)

    # Consume 10 tokens
    assert bucket.acquire(10.0, timeout=0) is True
    assert bucket.current_tokens() == 50.0

    # Advance clock by 5 seconds -> should refill 5 tokens
    current_time += 5.0
    assert bucket.current_tokens() == 55.0

    # Advance clock by 100 seconds -> should not exceed capacity (60)
    current_time += 100.0
    assert bucket.current_tokens() == 60.0


def test_token_bucket_acquire_timeout() -> None:
    current_time = 1000.0

    def clock() -> float:
        return current_time

    bucket = TokenBucket(requests_per_minute=60, clock=clock)

    # Exhaust all 60 tokens
    assert bucket.acquire(60.0, timeout=0) is True
    assert bucket.current_tokens() == 0.0

    # Trying to acquire 5 tokens with timeout 0 should fail
    assert bucket.acquire(5.0, timeout=0) is False

    # Advance clock by 2 seconds -> only 2 tokens available, still not 5
    current_time += 2.0
    assert bucket.acquire(5.0, timeout=0.1) is False

    # Advance clock by 4 more seconds -> 6 tokens available, can acquire 5
    current_time += 4.0
    assert bucket.acquire(5.0, timeout=0) is True
    assert bucket.current_tokens() == 1.0


@pytest.mark.asyncio
async def test_token_bucket_async_aacquire() -> None:
    current_time = 1000.0

    def clock() -> float:
        return current_time

    bucket = TokenBucket(requests_per_minute=120, clock=clock)  # 2 tokens/s

    assert await bucket.aacquire(10.0, timeout=0) is True
    assert bucket.current_tokens() == 110.0

    # Exhaust
    assert await bucket.aacquire(110.0, timeout=0) is True
    assert bucket.current_tokens() == 0.0

    # Cannot acquire with 0 timeout
    assert await bucket.aacquire(1.0, timeout=0) is False


def test_concurrency_limiter_sync_acquire_release() -> None:
    limiter = ConcurrencyLimiter(max_concurrency=2)
    assert limiter.max_concurrency == 2
    assert limiter.current_in_flight == 0

    assert limiter.acquire(timeout=0.1) is True
    assert limiter.current_in_flight == 1

    assert limiter.acquire(timeout=0.1) is True
    assert limiter.current_in_flight == 2

    # Third acquire should timeout
    assert limiter.acquire(timeout=0.05) is False
    assert limiter.current_in_flight == 2

    # Release one slot
    limiter.release()
    assert limiter.current_in_flight == 1

    # Now acquire succeeds
    assert limiter.acquire(timeout=0.1) is True
    assert limiter.current_in_flight == 2

    limiter.release()
    limiter.release()
    assert limiter.current_in_flight == 0


def test_concurrency_limiter_context_manager_exception_safety() -> None:
    limiter = ConcurrencyLimiter(max_concurrency=1)

    with pytest.raises(ValueError), limiter.concurrency():
        assert limiter.current_in_flight == 1
        raise ValueError("boom")

    # In-flight count must be 0 even after exception
    assert limiter.current_in_flight == 0
    assert limiter.acquire(timeout=0.1) is True
    limiter.release()


@pytest.mark.asyncio
async def test_concurrency_limiter_async_context_manager() -> None:
    limiter = ConcurrencyLimiter(max_concurrency=2)

    async with limiter.aconcurrency():
        assert limiter.current_in_flight == 1
        async with limiter.aconcurrency():
            assert limiter.current_in_flight == 2
            # A third concurrent task should timeout
            assert await limiter.aacquire(timeout=0.05) is False

    assert limiter.current_in_flight == 0


def test_make_limiter_key_hashing() -> None:
    # Empty / None key
    assert make_limiter_key("glm") == "glm:default"
    assert make_limiter_key("glm", None) == "glm:default"
    assert make_limiter_key("GLM", "   ") == "glm:default"

    # Same key yields same hash
    k1 = make_limiter_key("glm", "sk-1234567890abcdef")
    k2 = make_limiter_key("GLM", "sk-1234567890abcdef")
    assert k1 == k2
    assert k1.startswith("glm:")
    assert len(k1) == len("glm:") + 16

    # Different key yields different hash
    k3 = make_limiter_key("glm", "sk-different-key")
    assert k1 != k3


def test_rate_limit_registry_configure_and_get() -> None:
    registry = RateLimitRegistry()
    key = make_limiter_key("glm", "sk-test")

    cfg1 = ProviderRateLimitConfig(
        requests_per_minute=100,
        max_concurrent_requests=5,
        retry_max_attempts=4,
    )
    limiter = registry.configure(key, cfg1)

    assert limiter.token_bucket is not None
    assert limiter.token_bucket.capacity == 100.0
    assert limiter.concurrency_limiter is not None
    assert limiter.concurrency_limiter.max_concurrency == 5
    assert limiter.config.retry_max_attempts == 4

    # Getting by key returns the exact same instance
    assert registry.get(key) is limiter

    # Update config dynamically
    cfg2 = ProviderRateLimitConfig(
        requests_per_minute=200,
        max_concurrent_requests=10,
    )
    updated = registry.configure(key, cfg2)
    assert updated is limiter
    assert limiter.token_bucket.capacity == 200.0
    assert limiter.concurrency_limiter.max_concurrency == 10


def test_rate_limit_registry_reset() -> None:
    registry = RateLimitRegistry()
    registry.configure("k1", ProviderRateLimitConfig(requests_per_minute=50))
    assert registry.get("k1").token_bucket is not None

    registry.reset()
    # After reset, get("k1") returns a clean unconstrained limiter
    fresh = registry.get("k1")
    assert fresh.token_bucket is None
    assert fresh.concurrency_limiter is None


@pytest.mark.asyncio
async def test_shared_limiter_across_concurrent_tasks() -> None:
    # 2 concurrent limit, 4 tasks attempting to run concurrently
    limiter = ConcurrencyLimiter(max_concurrency=2)
    active_peaks: list[int] = []

    async def worker() -> None:
        async with limiter.aconcurrency():
            active_peaks.append(limiter.current_in_flight)
            await asyncio.sleep(0.05)

    await asyncio.gather(worker(), worker(), worker(), worker())

    # Concurrency never exceeded 2
    assert max(active_peaks) <= 2
    assert limiter.current_in_flight == 0
