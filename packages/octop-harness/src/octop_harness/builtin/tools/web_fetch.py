"""Built-in tool: ``web_fetch`` — fetch a URL and convert HTML to markdown."""

from __future__ import annotations

from urllib.parse import urljoin

import httpx
from langchain_core.tools import tool
from markdownify import markdownify

from octop_harness.security.ssrf import UnsafeAgentFetchUrlError, validate_agent_fetch_url

_DEFAULT_TIMEOUT_S = 20.0
_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB hard cap to keep tool output bounded
_MAX_REDIRECTS = 10


def _fetch_public_url(url: str, *, timeout: float) -> httpx.Response:
    """GET ``url`` while blocking private/LAN targets on every hop."""
    current = validate_agent_fetch_url(url)
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            validate_agent_fetch_url(current)
            response = client.get(current)
            if 300 <= response.status_code < 400:
                location = (response.headers.get("location") or "").strip()
                if not location:
                    return response
                current = urljoin(str(response.request.url), location)
                continue
            return response
    raise UnsafeAgentFetchUrlError(f"exceeded {_MAX_REDIRECTS} redirects for {url!r}")


def _response_body_as_text(response: httpx.Response) -> str:
    """Convert a successful HTTP response into tool-visible text (or Error:)."""
    if response.is_error:
        return f"Error: HTTP {response.status_code} {response.reason_phrase} for {response.request.url}"
    content_type = response.headers.get("content-type", "").lower()
    body = response.content
    if len(body) > _MAX_BYTES:
        return f"Error: web_fetch response is {len(body)} bytes, exceeding the {_MAX_BYTES}-byte cap."
    text = response.text
    if "html" in content_type:
        return markdownify(text, heading_style="ATX").strip()
    return text.strip()


@tool
def web_fetch(url: str, timeout: float | None = None) -> str:
    """Fetch a URL and return its content as markdown.

    Args:
        url: The URL to fetch. Must use ``http`` or ``https``. Private,
            loopback, and link-local addresses are rejected (SSRF guard).
        timeout: Optional per-request timeout in seconds (default 20).

    Returns:
        Markdown-formatted text on success. HTML responses are converted
        via ``markdownify``; non-HTML responses are returned as plain
        text. **All recoverable failures return a plain-text string
        starting with ``"Error: "``** rather than raising — this keeps
        the agent's tool loop alive so the model can read the error and
        try a different URL/tool. Covered: non-http(s) scheme, oversized
        body, HTTP 4xx/5xx, DNS / connection failures, timeouts, and
        blocked private/LAN targets.
    """
    if not (url.startswith("http://") or url.startswith("https://")):
        return f"Error: web_fetch requires http(s) URL, got {url!r}"

    request_timeout = timeout if timeout is not None else _DEFAULT_TIMEOUT_S

    try:
        response = _fetch_public_url(url, timeout=request_timeout)
    except UnsafeAgentFetchUrlError as exc:
        return f"Error: {exc}"
    except httpx.HTTPError as exc:
        # Network-layer issues: DNS lookup, connection refused, timeout,
        # TLS error, …. Surface them as plain-text so the agent can
        # decide whether to retry, switch URLs, or give up gracefully
        # rather than crashing the whole graph.
        return f"Error: {type(exc).__name__}: {exc}"

    return _response_body_as_text(response)
