"""Unit tests for backoff delay calculation, Retry-After header parsing, and error detection."""

from __future__ import annotations

from types import SimpleNamespace

from octop.infra.agents.providers.backoff import (
    calculate_backoff_delay,
    extract_retry_after,
    is_retryable_provider_error,
    is_transient_rate_limit,
    is_transient_server_error,
)


def test_is_transient_rate_limit_detection() -> None:
    # HTTP 429 status code on exception
    exc_status = SimpleNamespace(status_code=429)
    assert is_transient_rate_limit(exc_status)  # type: ignore[arg-type]

    # HTTP 429 on response attribute
    exc_resp = SimpleNamespace(response=SimpleNamespace(status_code=429))
    assert is_transient_rate_limit(exc_resp)  # type: ignore[arg-type]

    # GLM 1302 error code
    exc_glm = RuntimeError("Error code: 1302 - {'error': {'message': '系统繁忙，请稍后再试'}}")
    assert is_transient_rate_limit(exc_glm)

    # GLM Chinese error message
    exc_busy = RuntimeError("模型接口调用失败：系统繁忙，请重试")
    assert is_transient_rate_limit(exc_busy)

    # Standard RateLimitError text
    exc_text = RuntimeError("RateLimitError: Requests per minute limit exceeded")
    assert is_transient_rate_limit(exc_text)

    # Non-rate-limit errors
    assert not is_transient_rate_limit(RuntimeError("Invalid API Key: 401 unauthorized"))
    assert not is_transient_rate_limit(RuntimeError("Context length exceeded"))


def test_is_transient_server_error_detection() -> None:
    assert is_transient_server_error(TimeoutError("connection timed out"))
    assert is_transient_server_error(ConnectionError("connection reset by peer"))
    assert is_transient_server_error(SimpleNamespace(status_code=502))  # type: ignore[arg-type]
    assert is_transient_server_error(SimpleNamespace(status_code=503))  # type: ignore[arg-type]
    assert is_transient_server_error(RuntimeError("504 Gateway Timeout"))

    assert not is_transient_server_error(RuntimeError("400 Bad Request"))
    assert not is_transient_server_error(RuntimeError("403 Forbidden"))


def test_is_retryable_provider_error() -> None:
    # 429 rate limit is retryable
    assert is_retryable_provider_error(SimpleNamespace(status_code=429))  # type: ignore[arg-type]
    # GLM 1302 is retryable
    assert is_retryable_provider_error(RuntimeError("1302: 系统繁忙"))
    # 503 is retryable
    assert is_retryable_provider_error(SimpleNamespace(status_code=503))  # type: ignore[arg-type]

    # 401 Auth is NOT retryable
    assert not is_retryable_provider_error(RuntimeError("401 Unauthorized"))
    # 422 Invalid parameter is NOT retryable
    assert not is_retryable_provider_error(RuntimeError("422 Validation Error"))


def test_extract_retry_after_from_attribute() -> None:
    exc = SimpleNamespace(retry_after=4.5)
    assert extract_retry_after(exc) == 4.5  # type: ignore[arg-type]


def test_extract_retry_after_from_headers() -> None:
    # Integer seconds
    exc1 = SimpleNamespace(response=SimpleNamespace(headers={"Retry-After": "12"}))
    assert extract_retry_after(exc1) == 12.0  # type: ignore[arg-type]

    # Float seconds
    exc2 = SimpleNamespace(response=SimpleNamespace(headers={"retry-after": "3.5"}))
    assert extract_retry_after(exc2) == 3.5  # type: ignore[arg-type]

    # Milliseconds header variant
    exc3 = SimpleNamespace(response=SimpleNamespace(headers={"retry-after-ms": "2500"}))
    assert extract_retry_after(exc3) == 2.5  # type: ignore[arg-type]


def test_extract_retry_after_from_error_message() -> None:
    assert (
        extract_retry_after(RuntimeError("Rate limit exceeded. Please retry after 5 seconds"))
        == 5.0
    )
    assert extract_retry_after(RuntimeError("Rate limit reached. Try again in 2.5s.")) == 2.5
    assert extract_retry_after(RuntimeError("Quota exceeded, retry in 10s")) == 10.0
    assert extract_retry_after(RuntimeError("Regular error without retry info")) is None


def test_calculate_backoff_delay_exponential_growth() -> None:
    # Deterministic test with jitter=False
    d0 = calculate_backoff_delay(0, base_delay=1.0, max_delay=60.0, jitter=False)
    d1 = calculate_backoff_delay(1, base_delay=1.0, max_delay=60.0, jitter=False)
    d2 = calculate_backoff_delay(2, base_delay=1.0, max_delay=60.0, jitter=False)
    d3 = calculate_backoff_delay(3, base_delay=1.0, max_delay=60.0, jitter=False)

    assert d0 == 1.0  # 1 * 2^0
    assert d1 == 2.0  # 1 * 2^1
    assert d2 == 4.0  # 1 * 2^2
    assert d3 == 8.0  # 1 * 2^3


def test_calculate_backoff_delay_max_cap() -> None:
    d = calculate_backoff_delay(10, base_delay=1.0, max_delay=15.0, jitter=False)
    assert d == 15.0  # Capped at max_delay


def test_calculate_backoff_delay_respects_retry_after() -> None:
    # Upstream gave 7.5s Retry-After
    d_no_jitter = calculate_backoff_delay(0, retry_after=7.5, jitter=False)
    assert d_no_jitter == 7.5

    # With jitter, should be within [7.5, 7.5 + 0.75]
    d_jitter = calculate_backoff_delay(0, retry_after=7.5, jitter=True)
    assert 7.5 <= d_jitter <= 8.5


def test_calculate_backoff_delay_full_jitter_bounds() -> None:
    # Full jitter must stay between 0 and ceiling
    for attempt in range(5):
        ceiling = 1.0 * (2**attempt)
        d = calculate_backoff_delay(attempt, base_delay=1.0, max_delay=60.0, jitter=True)
        assert 0.0 <= d <= ceiling
