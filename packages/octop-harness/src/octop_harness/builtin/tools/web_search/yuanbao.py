"""Yuanbao Search (Tencent Cloud WSA ``SearchPro``).

Requires ``TENCENTCLOUD_WSA_APIKEY``. Calls the service API-key endpoint
so the agent does not implement Tencent Cloud TC3 request signing.

https://cloud.tencent.com/document/product/1806/130615
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from langchain_core.tools import tool

DEFAULT_TIMEOUT = 30.0
DEFAULT_ENDPOINT = "https://api.wsa.cloud.tencent.com/SearchPro"
_QUERY_MAX_BYTES = 1500
# SearchPro only accepts these page sizes. Smaller asks snap up to 10.
_CNT_CHOICES = (10, 20, 30, 40, 50)


def _snap_cnt(max_results: int) -> int | None:
    if max_results < 1:
        return None
    for choice in _CNT_CHOICES:
        if max_results <= choice:
            return choice
    return _CNT_CHOICES[-1]


_KNOWN_ERRORS = {
    "UnauthorizedOperation": ("Error: Yuanbao Search authentication failed. Check TENCENTCLOUD_WSA_APIKEY."),
    "AuthFailure": "Error: Yuanbao Search authentication failed. Check TENCENTCLOUD_WSA_APIKEY.",
    "ResourceNotFound": "Error: Yuanbao Search is not activated for this account.",
    "ResourceUnavailable": ("Error: Yuanbao Search is unavailable. Check whether the account is in arrears."),
    "RequestLimitExceeded": "Error: Yuanbao Search rate limit reached. Retry later.",
}


def _error_dict(body: Any) -> dict[str, Any] | None:
    if not isinstance(body, dict):
        return None
    response = body.get("Response")
    error = response.get("Error") if isinstance(response, dict) else None
    if not isinstance(error, dict):
        error = body.get("Error")
    return error if isinstance(error, dict) else None


def _error_from_body(body: Any) -> str | None:
    error = _error_dict(body)
    if error is None:
        return None
    code = str(error.get("Code") or "Error")
    known = _KNOWN_ERRORS.get(code)
    if known is not None:
        return known
    message = str(error.get("Message") or "").strip()
    detail = f"{code}: {message}" if message else code
    return f"Error: Yuanbao Search failed ({detail})."


def _pages(body: Any) -> tuple[list[dict[str, Any]], str]:
    response = body.get("Response") if isinstance(body, dict) else None
    if not isinstance(response, dict):
        return [], ""
    raw_pages = response.get("Pages")
    msg = response.get("Msg")
    hint = msg.strip() if isinstance(msg, str) else ""
    if not isinstance(raw_pages, list):
        return [], hint
    parsed: list[dict[str, Any]] = []
    for item in raw_pages:
        page: Any = item
        if isinstance(item, str):
            try:
                page = json.loads(item)
            except ValueError:
                continue
        if isinstance(page, dict):
            parsed.append(page)
    return parsed, hint


def _slim(page: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for src, dst in (
        ("title", "title"),
        ("url", "url"),
        ("passage", "snippet"),
        ("site", "site"),
        ("date", "date"),
        ("score", "score"),
    ):
        value = page.get(src)
        if value not in (None, ""):
            out[dst] = value
    if "snippet" not in out and page.get("content") not in (None, ""):
        out["snippet"] = page["content"]
    return out


def _prepare(query: str, max_results: int) -> tuple[str, int] | str:
    clean_query = query.strip()
    if not clean_query:
        return "Error: Yuanbao Search query must not be empty."
    if len(clean_query.encode("utf-8")) > _QUERY_MAX_BYTES:
        return "Error: Yuanbao Search query must be at most 1500 UTF-8 bytes."
    cnt = _snap_cnt(max_results)
    if cnt is None:
        return "Error: Yuanbao Search max_results must be at least 1."
    return clean_query, cnt


def _render(response: httpx.Response) -> str:
    if response.status_code in {401, 403}:
        return "Error: Yuanbao Search authentication failed. Check TENCENTCLOUD_WSA_APIKEY."
    if response.status_code >= 400:
        return f"Error: Yuanbao Search returned HTTP {response.status_code}."
    try:
        body = response.json()
    except ValueError:
        return "Error: Yuanbao Search returned a non-JSON response."
    failure = _error_from_body(body)
    if failure is not None:
        return failure
    pages, hint = _pages(body)
    results: list[dict[str, Any]] = []
    for page in pages:
        item = _slim(page)
        if item:
            results.append(item)
    if results:
        return json.dumps(results, ensure_ascii=False)
    return f"No results found. {hint}" if hint else "No results found."


@tool
async def yuanbao_search(query: str, max_results: int = 10) -> str:
    """Search the open web with Tencent Yuanbao Search.

    Requires ``TENCENTCLOUD_WSA_APIKEY``. Results are a JSON array of
    ``{title, url, snippet, site, date, score}`` objects. Yuanbao only
    returns 10, 20, 30, 40, or 50 hits; a smaller ``max_results`` is
    raised to 10.

    Args:
        query: Search query. At most 1500 UTF-8 bytes.
        max_results: Desired hit count. Snapped to the next allowed page size.

    Returns:
        A JSON array of results, ``"No results found."``, or a plain-text
        error when the key is missing or the upstream call fails.
    """
    api_key = os.getenv("TENCENTCLOUD_WSA_APIKEY", "").strip()
    if not api_key:
        return "Error: TENCENTCLOUD_WSA_APIKEY environment variable is not set."
    prepared = _prepare(query, max_results)
    if isinstance(prepared, str):
        return prepared
    clean_query, cnt = prepared
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(
                DEFAULT_ENDPOINT,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"Query": clean_query, "Cnt": cnt},
            )
    except httpx.HTTPError as exc:
        return f"Error: Yuanbao Search request failed: {exc}"
    return _render(response)
