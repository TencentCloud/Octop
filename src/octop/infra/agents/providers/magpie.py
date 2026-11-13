"""Magpie local-gateway identity, discovery, and catalog mapping.

Magpie is an OpenAI-compatible provider. Discovery is a read-only probe of the
Octop host (not the dashboard browser). Session attribution uses
``X-Magpie-Session`` at turn time; this module never persists a static session
value into provider headers.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

MAGPIE_PRESET_ID = "magpie"
MAGPIE_PRESET_NAME = "Magpie"
MAGPIE_INTEGRATION = "magpie"
MAGPIE_DEFAULT_HOST = "127.0.0.1"
MAGPIE_DEFAULT_PORT = 3425
MAGPIE_DEFAULT_SCHEME = "http"
MAGPIE_DEFAULT_API_PATH = "/v1"
MAGPIE_DEFAULT_BASE_URL = "http://127.0.0.1:3425/v1"
MAGPIE_HELLO_URL = "http://127.0.0.1:3425/api/hello"
MAGPIE_LOCAL_API_KEY = "magpie-octop"
MAGPIE_SESSION_HEADER = "X-Magpie-Session"
MAGPIE_HELLO_TIMEOUT_S = 1.0

_MAGPIE_PRESET_KEYS = frozenset({MAGPIE_PRESET_ID, MAGPIE_PRESET_NAME, MAGPIE_PRESET_NAME.lower()})
_KNOWN_REASONING_ADAPTERS = frozenset(
    {
        "status_only",
        "thinking",
        "thinking_nested_effort",
        "openai_reasoning_effort",
        "anthropic_adaptive",
        "anthropic_budget",
        "dashscope",
        "openrouter",
    }
)
_CHAT_MODALITIES = frozenset({"text", "image", "audio"})
_NON_CHAT_TYPES = frozenset({"embedding", "image", "video", "audio", "rerank"})
_NON_CHAT_ID_HINTS = (
    "embed",
    "bge-",
    "e5-",
    "gte-",
    "rerank",
    "dall-e",
    "tts-",
    "whisper",
    "imagen",
    "sora",
)


@dataclass(frozen=True)
class MagpieDiscovery:
    """Result of the local Magpie hello probe."""

    available: bool
    base_url: str = MAGPIE_DEFAULT_BASE_URL
    version: str | None = None


@dataclass(frozen=True)
class MagpieSyncPlan:
    """Catalog diff applied only after the user confirms a refresh."""

    models: list[dict[str, Any]]
    added: list[str]
    removed: list[str]


def magpie_user_agent() -> str:
    """``User-Agent`` Magpie uses to attribute traffic to this Octop install."""
    from octop import __version__

    return f"Octop/{__version__}"


def magpie_preset() -> dict[str, Any]:
    """Octop-owned Magpie preset: empty catalog, local default URL, no models."""
    return {
        "id": MAGPIE_PRESET_ID,
        "name": MAGPIE_PRESET_NAME,
        "base_url": MAGPIE_DEFAULT_BASE_URL,
        "protocol": "openai",
        "api_key_prefix": "",
        "default_api_key": MAGPIE_LOCAL_API_KEY,
        "integration": MAGPIE_INTEGRATION,
        "models": [],
        "logo_id": MAGPIE_PRESET_ID,
    }


def extra_dict(extra: Any) -> dict[str, Any]:
    """Normalize ``extra_json`` / extra dict input."""
    if isinstance(extra, dict):
        return extra
    return {}


def is_magpie_default_base_url(base_url: Any) -> bool:
    """True only for the Magpie default OpenAI base (scheme/host/port/path)."""
    if not base_url:
        return False
    try:
        parsed = urlsplit(str(base_url).strip())
    except ValueError:
        return False
    if parsed.scheme.lower() != MAGPIE_DEFAULT_SCHEME:
        return False
    host = (parsed.hostname or "").lower()
    if host != MAGPIE_DEFAULT_HOST:
        return False
    port = parsed.port if parsed.port is not None else 80
    if port != MAGPIE_DEFAULT_PORT:
        return False
    path = (parsed.path or "").rstrip("/") or "/"
    return path == MAGPIE_DEFAULT_API_PATH


def is_magpie_provider(
    *,
    provider_name: Any = None,
    base_url: Any = None,
    extra: Any = None,
) -> bool:
    """Identify Magpie: explicit integration, then preset name, then default URL."""
    blob = extra_dict(extra)
    integration = str(blob.get("integration") or "").strip().lower()
    if integration == MAGPIE_INTEGRATION:
        return True
    name = str(provider_name or "").strip()
    if name.lower() in _MAGPIE_PRESET_KEYS:
        return True
    return is_magpie_default_base_url(base_url)


def ensure_magpie_headers(
    headers: dict[str, str] | None,
    *,
    probe: bool = False,
) -> dict[str, str]:
    """Add Magpie User-Agent; optionally a throwaway session for probes.

    Existing User-Agent / session header values win (case-insensitive).
    Runtime chat sessions are injected by harness via ``session_header``.
    """
    out = dict(headers) if headers else {}
    if not any(key.lower() == "user-agent" for key in out):
        out["User-Agent"] = magpie_user_agent()
    if probe and not any(key.lower() == MAGPIE_SESSION_HEADER.lower() for key in out):
        out[MAGPIE_SESSION_HEADER] = uuid.uuid4().hex
    return out


def magpie_catalog_model(item: dict[str, Any]) -> dict[str, Any] | None:
    """Map one Magpie ``/v1/models`` item to an Octop model dict, or skip it.

    IDs are kept verbatim (including nested ``/``). Embedding / image / video
    entries are not imported as chat candidates. Missing capability fields stay
    unknown — names such as ``group/*`` are not used to infer vision or reasoning.
    """
    mid = item.get("id")
    if not isinstance(mid, str) or not mid.strip():
        return None
    mid = mid.strip()
    if _is_non_chat_catalog_item(item, mid):
        return None

    display = item.get("display_name")
    name = display.strip() if isinstance(display, str) and display.strip() else mid
    model: dict[str, Any] = {"id": mid, "name": name}

    context = _positive_int(item.get("context_window"))
    if context is not None:
        model["context_window"] = context

    max_tokens = _positive_int(item.get("max_output_tokens"))
    if max_tokens is not None:
        model["max_tokens"] = max_tokens

    inputs = _chat_input_modalities(item.get("modalities"))
    if inputs:
        model["input"] = inputs

    _apply_reasoning(model, item)
    return model


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and value > 0:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _modality_list(raw: Any) -> list[Any]:
    """Magpie sends ``{"input": [...]}``; older catalogs send a flat list."""
    if isinstance(raw, dict):
        raw = raw.get("input")
    return raw if isinstance(raw, list) else []


def _chat_input_modalities(raw: Any) -> list[str]:
    seen: list[str] = []
    for item in _modality_list(raw):
        token = str(item).strip().lower()
        if token in _CHAT_MODALITIES and token not in seen:
            seen.append(token)
    return seen


def _is_non_chat_catalog_item(item: dict[str, Any], model_id: str) -> bool:
    kind = str(item.get("type") or item.get("task") or "").strip().lower()
    if kind in _NON_CHAT_TYPES:
        return True
    lower_id = model_id.lower()
    if any(hint in lower_id for hint in _NON_CHAT_ID_HINTS):
        return True
    modalities = _modality_list(item.get("modalities"))
    if modalities:
        tokens = {str(m).strip().lower() for m in modalities if str(m).strip()}
        if tokens and "text" not in tokens:
            return True
    return False


def _model_id(item: dict[str, Any]) -> str:
    mid = item.get("id")
    if not isinstance(mid, str):
        return ""
    return mid.strip()


def initial_magpie_models(fetched: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Models for a first add. ``None`` when the catalog has no chat models.

    Imported rows are enabled so the user can pick them. Nothing here selects
    a preferred model or a route group.
    """
    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in fetched:
        if not isinstance(item, dict):
            continue
        mid = _model_id(item)
        if not mid or mid in seen:
            continue
        seen.add(mid)
        row = dict(item)
        row["id"] = mid
        row["enabled"] = True
        models.append(row)
    return models or None


def plan_magpie_sync(
    existing: list[dict[str, Any]],
    fetched: list[dict[str, Any]],
) -> MagpieSyncPlan:
    """Keep saved rows, append new ids, and list removals.

    Surviving rows keep enabled, capability overrides, and group visibility.
    New rows stay disabled until the user enables them. An empty catalog
    removes every saved id and must be confirmed by the caller.
    """
    saved: dict[str, dict[str, Any]] = {}
    for item in existing:
        if not isinstance(item, dict):
            continue
        mid = _model_id(item)
        if mid and mid not in saved:
            saved[mid] = dict(item)

    incoming: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in fetched:
        if not isinstance(item, dict):
            continue
        mid = _model_id(item)
        if not mid or mid in incoming:
            continue
        incoming[mid] = item
        order.append(mid)

    added = [mid for mid in order if mid not in saved]
    removed = [mid for mid in saved if mid not in incoming]
    merged: list[dict[str, Any]] = []
    for mid in order:
        if mid in saved:
            merged.append(saved[mid])
            continue
        fresh = dict(incoming[mid])
        fresh["id"] = mid
        fresh["enabled"] = False
        merged.append(fresh)
    return MagpieSyncPlan(models=merged, added=added, removed=removed)


def _apply_reasoning(model: dict[str, Any], item: dict[str, Any]) -> None:
    raw = item.get("reasoning_config")
    if not isinstance(raw, dict):
        raw = item.get("reasoning")
    if isinstance(raw, dict):
        adapter = str(raw.get("adapter") or "").strip()
        if adapter and adapter not in _KNOWN_REASONING_ADAPTERS:
            return
        if raw.get("supported") is False:
            return
        model["reasoning"] = True
        if adapter:
            model["reasoning_config"] = dict(raw)
        return
    if raw is True:
        model["reasoning"] = True


async def discover_local_magpie() -> MagpieDiscovery:
    """Probe ``GET /api/hello`` on the Octop host. Failures are ``available=false``."""
    import httpx

    unavailable = MagpieDiscovery(available=False)
    try:
        async with httpx.AsyncClient(
            timeout=MAGPIE_HELLO_TIMEOUT_S,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.get(MAGPIE_HELLO_URL)
    except Exception as exc:
        logger.info("magpie discovery failed: %r (%s)", exc, type(exc).__name__)
        return unavailable

    if response.status_code < 200 or response.status_code >= 300:
        return unavailable
    try:
        payload = response.json()
    except Exception:
        return unavailable
    if not isinstance(payload, dict) or payload.get("name") != MAGPIE_INTEGRATION:
        return unavailable
    version = payload.get("version")
    display = str(version).strip() if version is not None else ""
    return MagpieDiscovery(
        available=True,
        base_url=MAGPIE_DEFAULT_BASE_URL,
        version=display or None,
    )


__all__ = [
    "MAGPIE_DEFAULT_BASE_URL",
    "MAGPIE_HELLO_URL",
    "MAGPIE_INTEGRATION",
    "MAGPIE_LOCAL_API_KEY",
    "MAGPIE_PRESET_ID",
    "MAGPIE_PRESET_NAME",
    "MAGPIE_SESSION_HEADER",
    "MagpieDiscovery",
    "discover_local_magpie",
    "ensure_magpie_headers",
    "MagpieSyncPlan",
    "initial_magpie_models",
    "is_magpie_default_base_url",
    "is_magpie_provider",
    "magpie_catalog_model",
    "magpie_preset",
    "magpie_user_agent",
    "plan_magpie_sync",
]
