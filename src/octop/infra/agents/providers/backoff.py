"""Backoff retry calculation, upstream Retry-After parsing, and rate limit classification."""

from __future__ import annotations

import email.utils
import logging
import random
import re
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Markers indicating transient upstream rate limit / system busy
_RATE_LIMIT_MARKERS = (
    "429",
    "rate_limit",
    "rate limit",
    "ratelimit",
    "too many requests",
    "resource has been exhausted",
    "requests per minute",
    "concurrency limit",
    "1302",  # Zhipu GLM error code: 系统繁忙
    "系统繁忙",  # Zhipu GLM error message
    "system is busy",
)

_SERVER_ERROR_STATUSES = {500, 502, 503, 504}
_SERVER_ERROR_MARKERS = (
    "500",
    "502",
    "503",
    "504",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
    "internal server error",
)

_RETRY_AFTER_PATTERNS = (
    re.compile(
        r"(?:retry[- ]after|please retry in|retry in|wait)\s*(?:is\s*)?(\d+(?:\.\d+)?)\s*(?:s|sec|seconds)?",
        re.I,
    ),
    re.compile(r"try again in (\d+(?:\.\d+)?)s", re.I),
    re.compile(r"after (\d+(?:\.\d+)?) seconds", re.I),
    re.compile(r"resets in (\d+(?:\.\d+)?)s", re.I),
)


def _get_status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "status", "http_status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    response = getattr(exc, "response", None)
    if response is not None:
        for attr in ("status_code", "status"):
            val = getattr(response, attr, None)
            if isinstance(val, int):
                return val
    return None


def _get_header(exc: Exception, header_name: str) -> str | None:
    header_lower = header_name.lower()
    for obj in (exc, getattr(exc, "response", None)):
        if obj is None:
            continue
        headers = getattr(obj, "headers", None)
        if headers is None:
            continue
        if hasattr(headers, "get"):
            val = headers.get(header_name) or headers.get(header_lower)
            if val is not None:
                return str(val).strip()
    return None


def is_transient_rate_limit(exc: Exception) -> bool:
    """Return True if *exc* represents an upstream rate limit (429, GLM 1302, etc.)."""
    code = _get_status_code(exc)
    if code == 429:
        return True

    name = type(exc).__name__.lower()
    if "ratelimit" in name or "toomanyrequests" in name:
        return True

    msg = str(exc).lower()
    return any(marker in msg for marker in _RATE_LIMIT_MARKERS)


def is_transient_server_error(exc: Exception) -> bool:
    """Return True if *exc* represents a transient server/network outage (502, 503, timeout)."""
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True

    code = _get_status_code(exc)
    if code in _SERVER_ERROR_STATUSES:
        return True

    name = type(exc).__name__.lower()
    if any(k in name for k in ("connection", "timeout", "serviceunavailable", "gateway")):
        return True

    msg = str(exc).lower()
    return any(marker in msg for marker in _SERVER_ERROR_MARKERS)


def is_retryable_provider_error(exc: Exception) -> bool:
    """Return True if *exc* is eligible for automatic retry with backoff."""
    return is_transient_rate_limit(exc) or is_transient_server_error(exc)


def extract_retry_after(exc: Exception, *, max_delay: float = 120.0) -> float | None:
    """Extract wait time in seconds from Retry-After header or exception text if present."""
    # 1. Direct attribute on exception (e.g. OpenAI SDK)
    attr_delay = getattr(exc, "retry_after", None)
    if isinstance(attr_delay, (int, float)) and attr_delay > 0:
        return min(float(attr_delay), max_delay)

    # 2. HTTP response headers
    raw_header = _get_header(exc, "Retry-After")
    if raw_header:
        # Check integer/float seconds
        try:
            val = float(raw_header)
            if val > 0:
                return min(val, max_delay)
        except ValueError:
            # Check HTTP date format (e.g. "Wed, 21 Oct 2026 07:28:00 GMT")
            try:
                parsed_time = email.utils.parsedate_to_datetime(raw_header)
                diff = parsed_time.timestamp() - time.time()
                if diff > 0:
                    return min(diff, max_delay)
            except Exception:
                pass

    # Milliseconds header variant
    raw_ms = _get_header(exc, "retry-after-ms")
    if raw_ms:
        try:
            val = float(raw_ms) / 1000.0
            if val > 0:
                return min(val, max_delay)
        except ValueError:
            pass

    # 3. Regex search on error message text
    msg = str(exc)
    for pattern in _RETRY_AFTER_PATTERNS:
        match = pattern.search(msg)
        if match:
            try:
                seconds = float(match.group(1))
                if seconds > 0:
                    return min(seconds, max_delay)
            except ValueError:
                pass

    return None


def calculate_backoff_delay(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    *,
    retry_after: float | None = None,
    jitter: bool = True,
    rng: Callable[[float, float], float] = random.uniform,
) -> float:
    """Calculate exponential backoff delay with full jitter and Retry-After respect.

    When *retry_after* is provided, respects upstream hint with a small positive jitter
    to avoid lockstep reconnection collisions among concurrent agents.
    Otherwise uses the Full Jitter pattern: uniform(0, min(max_delay, base * 2^attempt)).
    """
    if retry_after is not None and retry_after > 0:
        delay = retry_after
        if jitter:
            # Small jitter (+0% to +10%, max 1s) to de-synchronize concurrent agents
            delay += rng(0.0, min(1.0, retry_after * 0.1))
        return min(max_delay, max(0.0, delay))

    ceiling = float(min(max_delay, base_delay * (2**attempt)))
    if jitter:
        return rng(0.0, ceiling)
    return ceiling


__all__ = [
    "calculate_backoff_delay",
    "extract_retry_after",
    "is_retryable_provider_error",
    "is_transient_rate_limit",
    "is_transient_server_error",
]
