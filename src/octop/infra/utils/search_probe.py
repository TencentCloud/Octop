"""Probe web-search provider API keys via direct HTTP (no env mutation).

Used by ``POST /api/search/{provider_id}/test``. Credentials come from the
request body and are never written to ``os.environ``.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Mapping
from typing import Any, Literal

import httpx

ErrorType = Literal["auth_error", "timeout", "network_error", "invalid_config", "unknown"]

_TIMEOUT_S = 30.0
_TEST_QUERY = "octop connectivity probe"
# Moonshot stopped serving ``moonshot-v1-*`` to new accounts, so the model has to
# be overridable without a release (#1926). Keep this in sync with the harness's
# ``builtin/tools/web_search/kimi.py``.
KIMI_MODEL_ENV = "MOONSHOT_SEARCH_MODEL"
DEFAULT_KIMI_MODEL = "kimi-k2.6"
_KNOWN: frozenset[str] = frozenset({"tavily", "brave", "google", "kimi"})
_REQUIRED: dict[str, tuple[str, ...]] = {
    "tavily": ("TAVILY_API_KEY",),
    "brave": ("BRAVE_API_KEY",),
    "google": ("GOOGLE_API_KEY", "GOOGLE_CSE_ID"),
    "kimi": ("MOONSHOT_API_KEY",),
}


def kimi_search_model(env_vars: Mapping[str, str] | None = None) -> str:
    """Model to test Kimi search with.

    The dashboard passes the saved env in the request body, so that wins; a
    server-side ``MOONSHOT_SEARCH_MODEL`` (``~/.octop/env``) is the fallback for
    self-hosted installs. Anything unset falls back to the current default.
    """
    for source in (env_vars or {}, os.environ):
        value = str(source.get(KIMI_MODEL_ENV, "")).strip()
        if value:
            return value
    return DEFAULT_KIMI_MODEL


async def probe_search_provider(
    provider_id: str,
    env_vars: Mapping[str, str],
) -> dict[str, Any]:
    """Run a one-shot search against ``provider_id`` using ``env_vars``.

    Returns a dict matching the dashboard ``TestSearchResponse`` shape.
    """
    started = time.perf_counter()
    try:
        outcome = await asyncio.wait_for(
            _probe(provider_id, env_vars),
            timeout=_TIMEOUT_S,
        )
    except TimeoutError:
        outcome = {
            "success": False,
            "error": f"probe timed out after {_TIMEOUT_S:.0f}s",
            "error_type": "timeout",
        }
    except Exception as exc:  # noqa: BLE001 — surface as probe failure
        outcome = {"success": False, "error": str(exc), "error_type": "unknown"}

    return {
        "provider_id": provider_id,
        "response_time_ms": int((time.perf_counter() - started) * 1000),
        **outcome,
    }


async def _probe(provider_id: str, env_vars: Mapping[str, str]) -> dict[str, Any]:
    if provider_id not in _KNOWN:
        return {
            "success": False,
            "error": f"Unknown search provider: {provider_id}",
            "error_type": "invalid_config",
        }

    missing = [k for k in _REQUIRED[provider_id] if not str(env_vars.get(k, "")).strip()]
    if missing:
        return {
            "success": False,
            "error": f"missing environment variable(s): {', '.join(missing)}",
            "error_type": "invalid_config",
        }

    creds = {k: str(env_vars[k]).strip() for k in _REQUIRED[provider_id]}
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        if provider_id == "tavily":
            return await _tavily(client, creds["TAVILY_API_KEY"])
        if provider_id == "brave":
            return await _brave(client, creds["BRAVE_API_KEY"])
        if provider_id == "google":
            return await _google(client, creds["GOOGLE_API_KEY"], creds["GOOGLE_CSE_ID"])
        return await _kimi(
            client,
            creds["MOONSHOT_API_KEY"],
            kimi_search_model(env_vars),
        )


async def _tavily(client: httpx.AsyncClient, api_key: str) -> dict[str, Any]:
    response = await client.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"query": _TEST_QUERY, "max_results": 1, "search_depth": "basic"},
    )
    return _from_response(response, provider="Tavily", results_key="results")


async def _brave(client: httpx.AsyncClient, api_key: str) -> dict[str, Any]:
    response = await client.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        },
        params={"q": _TEST_QUERY, "count": 1},
    )
    return _from_brave(response)


async def _google(client: httpx.AsyncClient, api_key: str, cse_id: str) -> dict[str, Any]:
    response = await client.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": api_key, "cx": cse_id, "q": _TEST_QUERY, "num": 1},
    )
    return _from_google(response)


async def _kimi(client: httpx.AsyncClient, api_key: str, model: str) -> dict[str, Any]:
    # ``$web_search`` is a Moonshot builtin function, hence
    # ``type="builtin_function"`` — a plain function name may not contain ``$``.
    # ``temperature`` is deliberately absent: the current models pin it
    # server-side and reject anything else with HTTP 400 (#1926).
    response = await client.post(
        "https://api.moonshot.cn/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": _TEST_QUERY}],
            "tools": [{"type": "builtin_function", "function": {"name": "$web_search"}}],
        },
    )
    return _from_kimi(response, model)


def _from_response(
    response: httpx.Response,
    *,
    provider: str,
    results_key: str,
) -> dict[str, Any]:
    fail = _http_failure(response)
    if fail is not None:
        return fail
    try:
        payload = response.json()
    except ValueError:
        return {"success": False, "error": "invalid JSON response", "error_type": "unknown"}
    count = 0
    if isinstance(payload, dict):
        raw = payload.get(results_key)
        count = len(raw) if isinstance(raw, list) else 1
    return {
        "success": True,
        "result_count": count,
        "message": f"{provider} search test successful",
    }


def _from_brave(response: httpx.Response) -> dict[str, Any]:
    fail = _http_failure(response)
    if fail is not None:
        return fail
    try:
        payload = response.json()
    except ValueError:
        return {"success": False, "error": "invalid JSON response", "error_type": "unknown"}
    web = payload.get("web") if isinstance(payload, dict) else None
    results = web.get("results") if isinstance(web, dict) else None
    count = len(results) if isinstance(results, list) else 1
    return {
        "success": True,
        "result_count": count,
        "message": "Brave search test successful",
    }


def _from_google(response: httpx.Response) -> dict[str, Any]:
    fail = _http_failure(response)
    if fail is not None:
        return fail
    try:
        payload = response.json()
    except ValueError:
        return {"success": False, "error": "invalid JSON response", "error_type": "unknown"}
    items = payload.get("items") if isinstance(payload, dict) else None
    count = len(items) if isinstance(items, list) else 0
    return {
        "success": True,
        "result_count": count,
        "message": "Google search test successful",
    }


def _from_kimi(response: httpx.Response, model: str) -> dict[str, Any]:
    fail = _kimi_failure(response, model)
    if fail is not None:
        return fail
    try:
        payload = response.json()
    except ValueError:
        return {"success": False, "error": "invalid JSON response", "error_type": "unknown"}
    choices = payload.get("choices") if isinstance(payload, dict) else None
    content = None
    searched = False
    if isinstance(choices, list) and choices:
        choice = choices[0] if isinstance(choices[0], dict) else {}
        message = choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            # ``$web_search`` is a builtin function, so a healthy reply to a
            # search prompt is a ``tool_calls`` turn rather than text: the
            # arguments the model produced *are* the search result.
            searched = bool(message.get("tool_calls"))
        searched = searched or choice.get("finish_reason") == "tool_calls"
    return {
        "success": True,
        "result_count": 1 if (content or searched) else 0,
        "message": f"Kimi search test successful (model: {model})",
    }


def _kimi_failure(response: httpx.Response, model: str) -> dict[str, Any] | None:
    """Translate Moonshot's errors into something the reader can act on.

    A retired or unentitled model comes back as ``404`` with
    ``resource_not_found_error`` and the ambiguous text "Not found the model
    ... or Permission denied", which leaves the reader unable to tell a bad
    key from an unavailable model (#1926).
    """
    if response.status_code < 400:
        return None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and error.get("type") == "resource_not_found_error":
        detail = str(error.get("message") or "resource_not_found_error")
        return {
            "success": False,
            "error": (
                f"Moonshot does not serve model {model!r} to this account "
                f"({detail}). Set {KIMI_MODEL_ENV} to a model the key can use."
            ),
            "error_type": "invalid_config",
        }
    return _http_failure(response)


def _http_failure(response: httpx.Response) -> dict[str, Any] | None:
    if response.status_code < 400:
        return None
    body = (response.text or "").strip()
    detail = body[:300] if body else response.reason_phrase
    error = f"HTTP {response.status_code}: {detail}"
    if response.status_code in {401, 403}:
        error_type: ErrorType = "auth_error"
    elif response.status_code == 429:
        error_type = "auth_error"
    else:
        error_type = "network_error" if response.status_code >= 500 else "unknown"
    return {"success": False, "error": error, "error_type": error_type}
