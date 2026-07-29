"""Provider connectivity probes (shared by API and CLI)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from types import SimpleNamespace
from typing import Any

import httpx

from octop.infra.agents.providers import KIND_TO_PROTOCOL

logger = logging.getLogger(__name__)

_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
_FETCH_MODELS_TIMEOUT_S = 30.0


def provider_headers(row: Any) -> dict[str, str]:
    raw = getattr(row, "extra_json", None)
    if not raw:
        return {}
    try:
        extra = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(extra, dict):
        return {}
    headers = extra.get("headers")
    return dict(headers) if isinstance(headers, dict) else {}


def _is_codex_base_url(base_url: str | None) -> bool:
    return bool(base_url and "chatgpt.com/backend-api/codex" in base_url)


def build_probe_chat_model(row: Any, *, model_id: str | None = None) -> Any:
    """Construct a chat model from a provider row for probing."""
    from harness_agent.config import ModelConfig, ProviderConfig
    from harness_agent.llm.factory import build_chat_model

    protocol = KIND_TO_PROTOCOL.get(row.kind, row.kind)
    headers = provider_headers(row)
    base_url = row.base_url or "https://api.openai.com/v1"
    models = row.get_models() if hasattr(row, "get_models") else []
    mid = model_id or (models[0]["id"] if models else "gpt-4o-mini")
    entry = next((m for m in models if m.get("id") == mid), None)
    display_name = (entry or {}).get("name") or mid
    model = ModelConfig(id=mid, name=display_name)

    if _is_codex_base_url(base_url):
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": model.id,
            "base_url": base_url,
            "api_key": row.api_key or "",
            "use_responses_api": True,
        }
        if headers:
            kwargs["default_headers"] = dict(headers)
        return ChatOpenAI(**kwargs)

    provider = ProviderConfig(
        id=row.name,
        name=row.name,
        protocol=protocol,
        base_url=base_url,
        api_key=row.api_key or "",
        headers=headers,
    )
    return build_chat_model(provider, model)


def make_probe_provider_row(
    *,
    name: str,
    kind: str,
    api_key: str | None,
    base_url: str | None,
    model_id: str,
    extra_json: str | None = None,
) -> Any:
    """Build a ProviderRow-like object for connectivity probes."""
    return SimpleNamespace(
        name=name,
        kind=kind,
        base_url=base_url,
        api_key=api_key,
        extra_json=extra_json,
        get_models=lambda: [{"id": model_id, "name": model_id}],
    )


async def probe_provider_row(row: Any, *, model_id: str | None = None) -> dict[str, Any]:
    """Probe a provider by sending a one-token ping and timing it."""
    started = time.perf_counter()
    try:
        chat = build_probe_chat_model(row, model_id=model_id)
        result = await asyncio.wait_for(chat.ainvoke("ping"), timeout=30.0)
    except Exception as exc:
        logger.info("provider probe failed for %s: %s", getattr(row, "name", "?"), exc)
        return {"ok": False, "error": str(exc)}
    latency_ms = int((time.perf_counter() - started) * 1000)
    _ = getattr(result, "content", None)
    return {"ok": True, "latency_ms": latency_ms}


def _models_list_url(base_url: str | None) -> str:
    root = (base_url or "").strip().rstrip("/") or _DEFAULT_OPENAI_BASE_URL
    return f"{root}/models"


async def fetch_openai_compatible_models(
    *,
    base_url: str | None,
    api_key: str,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """List models via OpenAI-compatible ``GET {base}/models``."""
    url = _models_list_url(base_url)
    headers: dict[str, str] = {"Authorization": f"Bearer {api_key}"}
    if extra_headers:
        headers.update(extra_headers)
    try:
        async with httpx.AsyncClient(timeout=_FETCH_MODELS_TIMEOUT_S) as client:
            response = await client.get(url, headers=headers)
    except Exception as exc:
        logger.info("provider fetch-models failed for %s: %s", url, exc)
        return {"ok": False, "error": str(exc)}

    if response.status_code >= 400:
        detail = response.text.strip()
        if len(detail) > 300:
            detail = detail[:300] + "…"
        error = f"HTTP {response.status_code}"
        if detail:
            error = f"{error}: {detail}"
        return {"ok": False, "error": error}

    try:
        payload = response.json()
    except Exception:
        return {
            "ok": False,
            "error": "response is not valid JSON (expected OpenAI-compatible /models)",
        }

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return {
            "ok": False,
            "error": "response is not OpenAI-compatible (expected {data: [{id, …}]})",
        }

    models: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        mid = item.get("id")
        if not isinstance(mid, str) or not mid.strip():
            continue
        mid = mid.strip()
        if mid in seen:
            continue
        seen.add(mid)
        models.append({"id": mid, "name": mid})
    models.sort(key=lambda m: m["id"])
    return {"ok": True, "models": models}
