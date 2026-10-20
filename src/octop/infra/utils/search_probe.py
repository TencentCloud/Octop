"""Probe web-search provider API keys via direct HTTP (no env mutation).

Used by ``POST /api/search/{provider_id}/test``. Credentials come from the
request body and are never written to ``os.environ``.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Any, Literal

import httpx

ErrorType = Literal["auth_error", "timeout", "network_error", "invalid_config", "unknown"]

_TIMEOUT_S = 30.0
_TEST_QUERY = "octop connectivity probe"
_KNOWN: frozenset[str] = frozenset({"tavily", "doubao", "deepseek", "exa", "kimi"})
_REQUIRED: dict[str, tuple[str, ...]] = {
    "tavily": ("TAVILY_API_KEY",),
    "doubao": ("DOUBAO_SEARCH_API_KEY",),
    "deepseek": ("DEEPSEEK_API_KEY",),
    "exa": ("EXA_API_KEY",),
    "kimi": ("MOONSHOT_API_KEY",),
}


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
        if provider_id == "doubao":
            return await _doubao(client, creds["DOUBAO_SEARCH_API_KEY"])
        if provider_id == "deepseek":
            return await _deepseek(client, creds["DEEPSEEK_API_KEY"])
        if provider_id == "exa":
            return await _exa(client, creds["EXA_API_KEY"])
        return await _kimi(client, creds["MOONSHOT_API_KEY"])


async def _tavily(client: httpx.AsyncClient, api_key: str) -> dict[str, Any]:
    response = await client.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"query": _TEST_QUERY, "max_results": 1, "search_depth": "basic"},
    )
    return _from_response(response, provider="Tavily", results_key="results")


async def _doubao(client: httpx.AsyncClient, api_key: str) -> dict[str, Any]:
    response = await client.post(
        "https://open.feedcoopapi.com/search_api/global_search",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            "SearchType": "web",
            "Query": _TEST_QUERY[:100],
            "DocCount": 1,
            "MaxSnippetLength": 300,
        },
    )
    return _from_doubao(response)


async def _deepseek(client: httpx.AsyncClient, api_key: str) -> dict[str, Any]:
    response = await client.post(
        "https://api.deepseek.com/v1/tools/search",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={"query": _TEST_QUERY[:128], "count": 1, "need_content": False},
    )
    return _from_response(response, provider="DeepSeek", results_key="results")


async def _exa(client: httpx.AsyncClient, api_key: str) -> dict[str, Any]:
    response = await client.post(
        "https://api.exa.ai/search",
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
        },
        json={"query": _TEST_QUERY, "numResults": 1, "contents": {"highlights": True}},
    )
    return _from_response(response, provider="Exa", results_key="results")


async def _kimi(client: httpx.AsyncClient, api_key: str) -> dict[str, Any]:
    response = await client.post(
        "https://api.moonshot.cn/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "moonshot-v1-128k",
            "messages": [{"role": "user", "content": _TEST_QUERY}],
            "tools": [{"type": "web_search"}],
            "temperature": 0.3,
        },
    )
    return _from_kimi(response)


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


def _from_doubao(response: httpx.Response) -> dict[str, Any]:
    fail = _http_failure(response)
    if fail is not None:
        return fail
    try:
        payload = response.json()
    except ValueError:
        return {"success": False, "error": "invalid JSON response", "error_type": "unknown"}
    # Business errors ride HTTP 200: ResponseMetadata.Error (API layer) and
    # Result.ErrorCode/ErrorMsg (search layer).
    meta = payload.get("ResponseMetadata") if isinstance(payload, dict) else None
    api_err = meta.get("Error") if isinstance(meta, dict) else None
    if isinstance(api_err, dict):
        code = api_err.get("Code", "unknown")
        message = api_err.get("Message", "")
        error_type: ErrorType = "auth_error" if code in {"10401", "10403", "700901"} else "unknown"
        return {
            "success": False,
            "error": f"doubao error {code}: {message}",
            "error_type": error_type,
        }
    result = payload.get("Result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return {"success": False, "error": "missing Result payload", "error_type": "unknown"}
    err_code = result.get("ErrorCode")
    if err_code not in (None, 0, "0"):
        error_type = (
            "auth_error" if str(err_code) in {"10403", "10406", "10408", "700901"} else "unknown"
        )
        return {
            "success": False,
            "error": f"doubao error {err_code}: {result.get('ErrorMsg', '')}",
            "error_type": error_type,
        }
    documents = result.get("Documents")
    count = len(documents) if isinstance(documents, list) else 0
    return {
        "success": True,
        "result_count": count,
        "message": "Doubao search test successful",
    }


def _from_kimi(response: httpx.Response) -> dict[str, Any]:
    fail = _http_failure(response)
    if fail is not None:
        return fail
    try:
        payload = response.json()
    except ValueError:
        return {"success": False, "error": "invalid JSON response", "error_type": "unknown"}
    choices = payload.get("choices") if isinstance(payload, dict) else None
    content = None
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = message.get("content")
    return {
        "success": True,
        "result_count": 1 if content else 0,
        "message": "Kimi search test successful",
    }


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
