"""Account-specific model discovery for the ChatGPT Codex endpoint."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import httpx

from octop.i18n import tr
from octop.infra.agents.providers.codex_oauth import (
    CODEX_ATTRIBUTION_VERSION,
    CODEX_BASE_URL,
    build_codex_headers,
)


def is_codex_endpoint(base_url: str | None) -> bool:
    try:
        endpoint = urlsplit((base_url or "").strip())
        port = endpoint.port
    except ValueError:
        return False
    return (
        endpoint.scheme == "https"
        and endpoint.hostname == "chatgpt.com"
        and port in (None, 443)
        and endpoint.path.rstrip("/") == "/backend-api/codex"
        and not endpoint.query
        and not endpoint.fragment
        and not endpoint.username
    )


def codex_catalog_params() -> dict[str, str]:
    return {"client_version": CODEX_ATTRIBUTION_VERSION}


def normalize_codex_catalog(payload: Any, *, locale: str = "en") -> list[dict[str, Any]]:
    data = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise ValueError(tr("codex_catalog.invalid_response", locale))
    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    valid_slugs = 0
    for item in data:
        if not isinstance(item, dict):
            continue
        slug = item.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            continue
        valid_slugs += 1
        slug = slug.strip()
        if item.get("visibility", "list") != "list":
            continue
        if slug in seen:
            continue
        seen.add(slug)
        name = item.get("display_name")
        modalities = item.get("input_modalities")
        inputs = (
            [v for v in modalities if v in ("text", "image")]
            if isinstance(modalities, list)
            else []
        )
        model: dict[str, Any] = {
            "id": slug,
            "name": name.strip() if isinstance(name, str) and name.strip() else slug,
            "enabled": True,
            "input": inputs or ["text"],
            "api_mode": "responses",
        }
        window = item.get("context_window")
        if isinstance(window, int) and not isinstance(window, bool) and window > 0:
            model["context_window"] = window
        models.append(model)
    if data and not valid_slugs:
        raise ValueError(tr("codex_catalog.invalid_response", locale))
    return models


def fetch_codex_catalog(access_token: str, account_id: str) -> list[dict[str, Any]]:
    headers = build_codex_headers(account_id)
    headers["Authorization"] = f"Bearer {access_token}"
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{CODEX_BASE_URL}/models", headers=headers, params=codex_catalog_params()
        )
        response.raise_for_status()
        models = normalize_codex_catalog(response.json())
    if not models:
        raise ValueError(tr("codex_catalog.empty"))
    return models
