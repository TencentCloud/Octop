"""Direct HTTP client for Tencent SkillHub marketplace rankings."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DEFAULT_SKILLHUB_HOST = "https://api.skillhub.cn"
RANKING_ENDPOINTS = {
    "hot": "/api/v1/showcase/hot",
    "featured": "/api/v1/showcase/featured",
    "newest": "/api/v1/showcase/newest",
    "recommended": "/api/v1/showcase/recommended",
    "trending": "/api/v1/showcase/trending",
    "paid": "/api/v1/showcase/paid",
}


class SkillHubMarketError(RuntimeError):
    """A SkillHub marketplace HTTP request failed."""


class SkillHubMarketTimeout(SkillHubMarketError):
    """A SkillHub marketplace HTTP request timed out."""


def _resolve_host(host: str | None) -> str:
    resolved = (host or "").strip() or os.environ.get("SKILLHUB_HOST", "").strip()
    resolved = (resolved or DEFAULT_SKILLHUB_HOST).rstrip("/")
    parsed = urlparse(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SkillHubMarketError(f"Invalid SkillHub API host: {resolved}")
    return resolved


def _fetch_ranking_json(
    host: str,
    ranking_type: str,
    *,
    timeout: float,
) -> dict[str, Any]:
    path = RANKING_ENDPOINTS.get(ranking_type)
    if path is None:
        raise SkillHubMarketError(f"Unsupported ranking type: {ranking_type}")

    url = f"{host}{path}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "octop-skillhub-market/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise SkillHubMarketError(
            f"Failed to fetch {ranking_type} rankings: HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise SkillHubMarketTimeout(f"Timed out fetching {ranking_type} rankings") from exc
        raise SkillHubMarketError(f"Failed to fetch {ranking_type} rankings: {exc.reason}") from exc
    except TimeoutError as exc:
        raise SkillHubMarketTimeout(f"Timed out fetching {ranking_type} rankings") from exc

    try:
        data = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SkillHubMarketError(f"Invalid JSON from {ranking_type} rankings: {exc}") from exc
    if not isinstance(data, dict):
        raise SkillHubMarketError(f"Ranking response must be a JSON object: {ranking_type}")
    return data


async def fetch_skillhub_rankings(
    ranking_type: str,
    *,
    host: str | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Fetch one ranking or all rankings directly over HTTP.

    ``all`` requests every section concurrently and returns successful sections
    even when another section fails. The optional ``errors`` map is additive to
    the existing CLI response shape and is ignored by older dashboard clients.
    """
    resolved_host = _resolve_host(host)
    if ranking_type != "all":
        return await asyncio.to_thread(
            _fetch_ranking_json,
            resolved_host,
            ranking_type,
            timeout=timeout,
        )

    names = list(RANKING_ENDPOINTS)
    rows = await asyncio.gather(
        *(
            asyncio.to_thread(
                _fetch_ranking_json,
                resolved_host,
                name,
                timeout=timeout,
            )
            for name in names
        ),
        return_exceptions=True,
    )
    rankings: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    failures: list[BaseException] = []
    for name, row in zip(names, rows, strict=True):
        if isinstance(row, asyncio.CancelledError):
            raise row
        if isinstance(row, BaseException):
            failures.append(row)
            errors[name] = str(row)
            logger.warning("SkillHub %s rankings failed: %s", name, row)
        else:
            rankings[name] = row

    if not rankings:
        if failures and all(isinstance(exc, SkillHubMarketTimeout) for exc in failures):
            raise SkillHubMarketTimeout("All SkillHub ranking requests timed out")
        detail = errors.get("hot") or next(iter(errors.values()), "unknown error")
        raise SkillHubMarketError(f"All SkillHub ranking requests failed: {detail}")

    result: dict[str, Any] = {"rankings": rankings}
    if errors:
        result["errors"] = errors
    return result


__all__ = [
    "RANKING_ENDPOINTS",
    "SkillHubMarketError",
    "SkillHubMarketTimeout",
    "fetch_skillhub_rankings",
]
