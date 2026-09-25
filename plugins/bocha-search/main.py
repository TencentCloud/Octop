"""Bocha web-search plugin (kind=tool) — one tool: ``bocha_search``.

How it fits Octop (copy demo-toolkit as template):

- Register the tool with ``ctx.tool(...)`` inside ``setup``.
- The API key is per-agent tool configuration (``config_fields``), edited in
  Dashboard → 工具管理 — never an environment variable.
- Wire format mirrors the merged Bocha provider in Tencent/WeKnora: Bing-style
  ``data.webPages.value[]`` with AI ``summary`` snippets, and an error body
  whose ``code`` is a *string* unlike the numeric success ``code``.
"""

from __future__ import annotations

from typing import Any

import httpx
from harness_agent.plugins import PluginContext, get_tool_config

BOCHA_SEARCH_URL = "https://api.bochaai.com/v1/web-search"

_TIMEOUT_S = 30.0
_DEFAULT_RESULTS = 10
_MAX_RESULTS = 50
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_DEFAULT_FRESHNESS = "noLimit"
_VALID_FRESHNESS = ("noLimit", "oneDay", "oneWeek", "oneMonth", "oneYear")


def clamp_results(max_results: int) -> int:
    """Clamp the requested result count to ``[1, 50]`` with 10 as default."""
    if max_results <= 0:
        return _DEFAULT_RESULTS
    return min(max_results, _MAX_RESULTS)


def validate_freshness(freshness: str) -> str:
    """Return the freshness enum value or raise ``ValueError``."""
    value = (freshness or "").strip() or _DEFAULT_FRESHNESS
    if value not in _VALID_FRESHNESS:
        raise ValueError(
            f"invalid freshness: {freshness!r} (expected one of {', '.join(_VALID_FRESHNESS)})"
        )
    return value


def build_payload(
    query: str,
    max_results: int,
    freshness: str,
    *,
    summary: bool = True,
) -> dict[str, Any]:
    """Build the Bocha request body. Raises on empty query / bad freshness."""
    text = (query or "").strip()
    if not text:
        raise ValueError("query is empty")
    return {
        "query": text,
        "freshness": validate_freshness(freshness),
        "summary": summary,
        "count": clamp_results(max_results),
    }


def parse_bocha_date(value: Any) -> str | None:
    """Parse Bocha date fields (three observed layouts) into ISO-8601."""
    text = str(value or "").strip()
    if not text:
        return None
    from datetime import datetime

    for layout in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, layout).isoformat()
        except ValueError:
            continue
    return None


def parse_results(payload: dict[str, Any], limit: int) -> list[dict[str, str]]:
    """Map a Bocha success payload to result dicts.

    - Success ``code`` is numeric ``200`` (or ``0``/``"200"`` defensively);
      any other code is an API-level error surfaced as ``ValueError``.
    - ``summary`` (AI 摘要) wins over ``snippet``; fall back to it.
    - Skip entries whose name and url are both empty; truncate to ``limit``.
    """
    code = payload.get("code")
    if code not in (0, 200, "200"):
        raise ValueError(f"Bocha API returned code {code}")
    data = payload.get("data")
    web_pages = data.get("webPages") if isinstance(data, dict) else None
    raw = web_pages.get("value") if isinstance(web_pages, dict) else None
    out: list[dict[str, str]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").strip()
        if not name and not url:
            continue
        snippet = str(item.get("summary") or "").strip()
        if not snippet:
            snippet = str(item.get("snippet") or "").strip()
        published = parse_bocha_date(item.get("datePublished"))
        if published is None:
            published = parse_bocha_date(item.get("dateLastCrawled"))
        row = {"title": name, "url": url, "snippet": snippet}
        if published:
            row["published"] = published
        out.append(row)
        if len(out) >= clamp_results(limit):
            break
    return out


def parse_error_body(status_code: int, body: str) -> str:
    """Extract detail from a Bocha error body (dual shape, then plain text).

    The error body carries ``message`` (or ``msg``) with a *string* code, unlike
    the numeric success code — both shapes must be tolerated (WeKnora #3036).
    """
    import json

    detail = ""
    try:
        payload = json.loads(body)
        if isinstance(payload, dict):
            detail = str(payload.get("message") or payload.get("msg") or "").strip()
    except ValueError:
        detail = ""
    if not detail:
        detail = (body or "").strip()
    if len(detail) > 4096:
        detail = detail[:4096]
    return (
        f"Bocha API returned status {status_code}: {detail}"
        if detail
        else (f"Bocha API returned status {status_code}")
    )


def _format_results(results: list[dict[str, str]]) -> str:
    if not results:
        return "No results found."
    lines = []
    for index, row in enumerate(results, start=1):
        header = row["title"] or row["url"]
        line = f"{index}. {header}\n   {row['url']}"
        if row["snippet"]:
            line += f"\n   {row['snippet']}"
        if row.get("published"):
            line += f"\n   published: {row['published']}"
        lines.append(line)
    return "\n\n".join(lines)


async def bocha_search(
    query: str,
    max_results: int = 10,
    freshness: str = "noLimit",
) -> str:
    """Search the web with Bocha AI (Bing-licensed, China-direct).

    Args:
        query: Search keywords.
        max_results: Desired result count (1-50, default 10).
        freshness: Time filter — noLimit / oneDay / oneWeek / oneMonth / oneYear.

    Returns:
        Numbered results with title, url, snippet (AI summary when present)
        and publish date, or an ``Error:`` description on failure.
    """
    cfg = get_tool_config("bocha_search") or {}
    api_key = str(cfg.get("api_key") or "").strip()
    if not api_key:
        return "Error: bocha_search is not configured — set api_key in Dashboard → 工具管理"

    try:
        payload = build_payload(query, max_results, freshness)
    except ValueError as exc:
        return f"Error: {exc}"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            response = await client.post(
                BOCHA_SEARCH_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        return f"Error: Bocha request failed: {exc}"

    body_bytes = response.content[: _MAX_RESPONSE_BYTES + 1]
    if len(body_bytes) > _MAX_RESPONSE_BYTES:
        return f"Error: Bocha response exceeds {_MAX_RESPONSE_BYTES} bytes"
    body = body_bytes.decode("utf-8", errors="replace")

    if response.status_code != 200:
        return f"Error: {parse_error_body(response.status_code, body)}"

    try:
        parsed = response.json()
    except ValueError:
        return "Error: invalid JSON response from Bocha"
    if not isinstance(parsed, dict):
        return "Error: unexpected Bocha response shape"

    try:
        results = parse_results(parsed, payload["count"])
    except ValueError as exc:
        return f"Error: {exc}"
    return _format_results(results)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "bocha_search",
        bocha_search,
        description="Search the web with Bocha AI (China-direct, Bing-licensed results with AI summaries)",
        config_fields=[
            {"name": "api_key", "type": "text", "required": True},
        ],
    )
