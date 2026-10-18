"""Async client for DeepSeek's web Search / Fetch APIs.

Reference: ``POST {base}/v1/tools/search`` and ``POST {base}/v1/tools/fetch``
(raw JSON, same Bearer auth as the DeepSeek chat API).

Design notes:

* The account-level QPS limit is 5 for each endpoint, so every HTTP request
  goes through a process-wide limiter per endpoint before it is sent.
* HTTP 408 / 429 / 5xx are transient; they are retried with exponential backoff
  (honouring ``Retry-After`` when present). Other 4xx errors are surfaced as
  readable, non-retryable failures.
* Nothing here raises into the agent loop: callers (the LangChain tools) catch
  :class:`DeepSeekSearchError` and return an ``Error: …`` string so one failed
  lookup cannot abort a turn.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from octop.infra.websearch.config import (
    MAX_FETCH_URL_CHARS,
    MAX_QUERY_CHARS,
    DeepSeekSearchConfig,
    clamp_count,
)

MAX_SEARCH_OUTPUT_CHARS = 20_000
MAX_FETCH_OUTPUT_CHARS = 30_000
# ``need_content=true`` can return full pages; keep each result bounded so a
# single search cannot blow up the model context.
MAX_RESULT_CONTENT_CHARS = 2_000
MAX_RESULT_SUMMARY_CHARS = 1_200

DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_ATTEMPTS = 3
MAX_RETRY_AFTER_S = 10.0


class RateLimiter(Protocol):
    """Minimal async limiter interface (one ``acquire`` per HTTP request)."""

    async def acquire(self) -> None: ...


class QpsLimiter:
    """Process-wide requests-per-second limiter (account level, per endpoint)."""

    def __init__(self, qps: float = 5.0) -> None:
        if qps <= 0:
            raise ValueError("qps must be positive")
        self._min_interval = 1.0 / qps
        self._lock: asyncio.Lock | None = None
        self._lock_loop: asyncio.AbstractEventLoop | None = None
        self._next_at = 0.0

    async def acquire(self) -> None:
        loop = asyncio.get_running_loop()
        # A fresh lock per event loop keeps the limiter usable from tests and
        # from short-lived loops without leaking a stale loop binding.
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
            self._next_at = 0.0
        async with self._lock:
            now = loop.time()
            wait = self._next_at - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = loop.time()
            self._next_at = now + self._min_interval


class NoopLimiter:
    """No-op limiter for tests and callers that enforce their own pacing."""

    async def acquire(self) -> None:
        return None


SEARCH_RATE_LIMITER: RateLimiter = QpsLimiter(5.0)
FETCH_RATE_LIMITER: RateLimiter = QpsLimiter(5.0)


class DeepSeekSearchError(RuntimeError):
    """A failed DeepSeek Search / Fetch request with a user-readable reason."""

    def __init__(
        self,
        message: str,
        *,
        error_type: str = "unknown",
        status_code: int | None = None,
        retryable: bool = False,
        operation: str = "request",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.status_code = status_code
        self.retryable = retryable
        # "search" | "fetch" — used to keep error hints accurate.
        self.operation = operation

    def readable(self) -> str:
        """Short, human-readable hint suitable for a tool error string."""
        status = f" (HTTP {self.status_code})" if self.status_code is not None else ""
        if self.error_type == "invalid_config":
            return f"DeepSeek search configuration error: {self.message}"
        if self.error_type == "auth_error":
            return (
                "DeepSeek API key is invalid or missing (HTTP 401). "
                "Update it in Settings → Models → Search."
            )
        if self.error_type == "insufficient_balance":
            return "DeepSeek account balance is insufficient (HTTP 402). Top up and retry."
        if self.error_type == "forbidden":
            if self.operation == "fetch":
                return f"DeepSeek refused to fetch this URL{status}: {self.message}"
            return f"DeepSeek rejected the search request{status}: {self.message}"
        if self.error_type == "not_found":
            if self.operation == "fetch":
                return (
                    f"DeepSeek could not extract page content for this URL{status}: {self.message}"
                )
            return f"DeepSeek search request failed{status}: {self.message}"
        if self.error_type == "timeout":
            return "DeepSeek request timed out. Retry in a moment."
        if self.error_type == "rate_limited":
            return "DeepSeek rate limit (HTTP 429) is still exceeded after retries. Retry later."
        if self.error_type == "server_error":
            return f"DeepSeek service error{status}: {self.message}"
        if self.error_type == "network_error":
            return f"DeepSeek request failed: {self.message}"
        return f"DeepSeek request failed{status}: {self.message}"


@dataclass(frozen=True)
class SearchResult:
    """One web result returned by ``/v1/tools/search``."""

    title: str
    url: str
    snippet: str = ""
    summary: str = ""
    content: str = ""
    site_name: str = ""
    site_icon: str = ""
    date: str = ""
    rerank_score: float = 0.0
    authority: int = -1

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> SearchResult:
        return cls(
            title=_as_text(payload.get("title")),
            url=_as_text(payload.get("url")),
            snippet=_as_text(payload.get("snippet")),
            summary=_as_text(payload.get("summary")),
            content=_as_text(payload.get("content")),
            site_name=_as_text(payload.get("site_name")),
            site_icon=_as_text(payload.get("site_icon")),
            date=_as_text(payload.get("date")),
            rerank_score=_as_float(payload.get("rerank_score")),
            authority=_as_int(payload.get("authority"), default=-1),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "summary": self.summary,
            "content": self.content,
            "site_name": self.site_name,
            "site_icon": self.site_icon,
            "date": self.date,
            "rerank_score": self.rerank_score,
            "authority": self.authority,
        }

    def prompt_block(self, index: int, *, include_content: bool) -> str:
        lines = [f"{index}. {self.title or '(untitled)'}", f"   URL: {self.url}"]
        meta = [
            f"site: {self.site_name or 'unknown'}",
            f"date: {self.date or 'unknown'}",
            f"rerank_score: {self.rerank_score:.1f}/3",
            f"authority: {self.authority if self.authority >= 0 else 'unknown'}"
            + ("/4" if self.authority >= 0 else ""),
        ]
        lines.append("   " + " | ".join(meta))
        summary = self.summary or self.snippet
        if summary:
            lines.append(f"   Summary: {_clip(summary, MAX_RESULT_SUMMARY_CHARS)}")
        if include_content and self.content:
            lines.append(f"   Content: {_clip(self.content, MAX_RESULT_CONTENT_CHARS)}")
        return "\n".join(lines)


@dataclass(frozen=True)
class FetchResult:
    """A page returned by ``/v1/tools/fetch``."""

    url: str
    title: str
    content: str


class DeepSeekSearchClient:
    """Small async client around the two DeepSeek web tools endpoints."""

    def __init__(
        self,
        config: DeepSeekSearchConfig,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        rng: random.Random | None = None,
        search_limiter: RateLimiter | None = None,
        fetch_limiter: RateLimiter | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self._config = config
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._transport = transport
        self._sleep: Callable[[float], Awaitable[None]] = sleep or asyncio.sleep
        self._rng: random.Random = rng if rng is not None else random.Random()
        self._search_limiter = search_limiter or SEARCH_RATE_LIMITER
        self._fetch_limiter = fetch_limiter or FETCH_RATE_LIMITER

    @property
    def config(self) -> DeepSeekSearchConfig:
        return self._config

    async def search(
        self,
        query: str,
        *,
        count: int | None = None,
        need_content: bool | None = None,
        localization: str | None = None,
    ) -> list[SearchResult]:
        """Run a web search; results are sorted by ``rerank_score`` first."""
        normalized = (query or "").strip()
        if not normalized:
            raise DeepSeekSearchError(
                "query must not be empty",
                error_type="invalid_config",
            )
        if len(normalized) > MAX_QUERY_CHARS:
            raise DeepSeekSearchError(
                f"query is {len(normalized)} characters; the limit is {MAX_QUERY_CHARS}",
                error_type="invalid_config",
            )

        use_content = self._config.need_content if need_content is None else need_content
        payload: dict[str, Any] = {
            "query": normalized,
            "count": clamp_count(count if count is not None else self._config.count),
            "need_content": bool(use_content),
        }
        loc = self._config.localization if localization is None else localization.strip()
        if loc:
            payload["localization"] = loc

        data = await self._post_json(
            url=self._config.search_url,
            payload=payload,
            limiter=self._search_limiter,
            operation="search",
        )
        raw_results = data.get("results")
        results = [
            SearchResult.from_payload(item)
            for item in (raw_results if isinstance(raw_results, list) else [])
            if isinstance(item, dict)
        ]
        # Higher rerank score first, then higher authority; stable for ties.
        results.sort(key=lambda item: (-item.rerank_score, -item.authority))
        return results

    async def fetch(self, url: str) -> FetchResult:
        """Fetch a single page and return its title + Markdown body."""
        normalized = (url or "").strip()
        _validate_fetch_url(normalized)
        data = await self._post_json(
            url=self._config.fetch_url,
            payload={"url": normalized},
            limiter=self._fetch_limiter,
            operation="fetch",
        )
        title = _as_text(data.get("title"))
        content = _as_text(data.get("content"))
        if not content.strip():
            raise DeepSeekSearchError(
                "response contained no page content",
                error_type="not_found",
                operation="fetch",
            )
        return FetchResult(url=normalized, title=title, content=content)

    async def _post_json(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        limiter: RateLimiter,
        operation: str,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        last_error: DeepSeekSearchError | None = None
        failed_response: httpx.Response | None = None
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            for attempt in range(1, self._max_attempts + 1):
                await limiter.acquire()
                failed_response = None
                try:
                    response = await client.post(url, headers=headers, json=payload)
                except httpx.TimeoutException:
                    last_error = DeepSeekSearchError(
                        f"request timed out after {self._timeout:.0f}s",
                        error_type="timeout",
                        retryable=True,
                    )
                except httpx.HTTPError as exc:
                    last_error = DeepSeekSearchError(
                        f"{type(exc).__name__}: {exc}",
                        error_type="network_error",
                        retryable=True,
                    )
                else:
                    if response.status_code < 400:
                        return _json_object(response)
                    last_error = _error_from_response(response, operation=operation)
                    if not last_error.retryable:
                        raise last_error
                    failed_response = response

                if attempt >= self._max_attempts:
                    break
                await self._sleep(self._backoff(attempt, failed_response))

        if last_error is None:  # pragma: no cover — defensive
            raise DeepSeekSearchError("DeepSeek request failed", error_type="unknown")
        raise last_error

    def _backoff(self, attempt: int, response: httpx.Response | None) -> float:
        """Retry delay: ``Retry-After`` when present, else exponential + jitter."""
        if response is not None:
            raw = (response.headers.get("retry-after") or "").strip()
            if raw:
                try:
                    return max(0.0, min(float(raw), MAX_RETRY_AFTER_S))
                except ValueError:
                    pass
        backoff = min(0.5 * float(2 ** (attempt - 1)), 4.0)
        return backoff + self._rng.uniform(0.0, 0.25)


def _validate_fetch_url(url: str) -> None:
    if not url:
        raise DeepSeekSearchError("url must not be empty", error_type="invalid_config")
    if len(url) > MAX_FETCH_URL_CHARS:
        raise DeepSeekSearchError(
            f"url is {len(url)} characters; the limit is {MAX_FETCH_URL_CHARS}",
            error_type="invalid_config",
        )
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise DeepSeekSearchError(
            f"url must be an absolute http(s) URL with a host, got {url!r}",
            error_type="invalid_config",
        )
    if parts.username is not None or parts.password is not None:
        raise DeepSeekSearchError(
            "url must not contain a username or password",
            error_type="invalid_config",
        )


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise DeepSeekSearchError(
            "DeepSeek returned a non-JSON response",
            error_type="unknown",
            status_code=response.status_code,
        ) from exc
    if not isinstance(data, dict):
        raise DeepSeekSearchError(
            "DeepSeek returned an unexpected response shape",
            error_type="unknown",
            status_code=response.status_code,
        )
    return data


def _error_from_response(
    response: httpx.Response,
    *,
    operation: str = "request",
) -> DeepSeekSearchError:
    message, _code = _error_payload(response)
    status = response.status_code
    detail = message or f"HTTP {status}"
    if status == 400:
        return DeepSeekSearchError(detail, error_type="invalid_config", status_code=status)
    if status == 401:
        return DeepSeekSearchError(detail, error_type="auth_error", status_code=status)
    if status == 402:
        return DeepSeekSearchError(detail, error_type="insufficient_balance", status_code=status)
    if status == 403:
        return DeepSeekSearchError(
            detail,
            error_type="forbidden",
            status_code=status,
            operation=operation,
        )
    if status == 404:
        return DeepSeekSearchError(
            detail,
            error_type="not_found",
            status_code=status,
            operation=operation,
        )
    if status == 408:
        return DeepSeekSearchError(detail, error_type="timeout", status_code=status, retryable=True)
    if status == 413:
        return DeepSeekSearchError(detail, error_type="invalid_config", status_code=status)
    if status == 429:
        return DeepSeekSearchError(
            detail, error_type="rate_limited", status_code=status, retryable=True
        )
    if status >= 500:
        return DeepSeekSearchError(
            detail, error_type="server_error", status_code=status, retryable=True
        )
    return DeepSeekSearchError(detail, error_type="unknown", status_code=status)


def _error_payload(response: httpx.Response) -> tuple[str, str | None]:
    """Extract the OpenAI-compatible ``error.message`` from a failed response."""
    raw = (response.text or "").strip()
    message = raw[:300] if raw else response.reason_phrase
    code: str | None = None
    try:
        data = response.json()
    except ValueError:
        return message, code
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            raw_message = error.get("message")
            if isinstance(raw_message, str) and raw_message.strip():
                message = raw_message.strip()[:300]
            raw_code = error.get("code")
            if isinstance(raw_code, str):
                code = raw_code
    return message, code


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _as_float(value: object, *, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_int(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _clip(text: str, limit: int) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1].rstrip() + "…"


def format_search_results(
    query: str,
    results: list[SearchResult],
    *,
    include_content: bool = False,
    max_chars: int = MAX_SEARCH_OUTPUT_CHARS,
) -> str:
    """Render search results as compact Markdown for the model."""
    if not results:
        return f'No web results found for "{query}".'
    header = (
        f'Web search results for "{query}" ({len(results)} results, strongest first; '
        "rerank_score 0-3 (>=1.5 is high quality), authority 0-4):"
    )
    blocks: list[str] = [header]
    used = len(header)
    for index, result in enumerate(results, 1):
        block = result.prompt_block(index, include_content=include_content)
        if used + len(block) > max_chars:
            blocks.append("... [remaining results truncated to fit the output budget]")
            break
        blocks.append(block)
        used += len(block) + 2
    return "\n\n".join(blocks)


def format_fetch_result(result: FetchResult, *, max_chars: int = MAX_FETCH_OUTPUT_CHARS) -> str:
    """Render a fetched page as Markdown for the model."""
    title = result.title.strip() or result.url
    text = f"Fetched page: {title}\nURL: {result.url}\n\n{result.content.strip()}"
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n\n…[content truncated]"
    return text


__all__ = [
    "FETCH_RATE_LIMITER",
    "MAX_FETCH_OUTPUT_CHARS",
    "MAX_SEARCH_OUTPUT_CHARS",
    "SEARCH_RATE_LIMITER",
    "DeepSeekSearchClient",
    "DeepSeekSearchError",
    "FetchResult",
    "NoopLimiter",
    "QpsLimiter",
    "RateLimiter",
    "SearchResult",
    "format_fetch_result",
    "format_search_results",
]
