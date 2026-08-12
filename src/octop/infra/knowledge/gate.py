"""Capability gate for the optional knowledge-base feature."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from octop.infra.agents.providers.model_flags import is_embedding_model
from octop.infra.agents.providers.onnx_service import (
    LOCAL_EMBEDDING_INSTALL_HINT,
    embedding_prerequisites_ok_for_model,
    is_model_downloaded,
    local_embedding_deps_available,
    require_embedding_prerequisites_for_model,
)

_FEATURE_ENABLED_KEY = "knowledge_bases_enabled"
_EMBEDDING_BACKEND_KEY = "knowledge_embedding_backend"
_EMBEDDING_MODEL_KEY = "knowledge_embedding_model"
_EMBEDDING_PROVIDER_ID_KEY = "knowledge_embedding_provider_id"

SettingsGet = Callable[[str], str | None]
SettingsSet = Callable[[str, str], None]


def _as_bool(value: str | None) -> bool:
    if value is None:
        return False
    try:
        decoded: Any = json.loads(value)
    except json.JSONDecodeError:
        decoded = value
    if isinstance(decoded, bool):
        return decoded
    return str(decoded).strip().lower() == "true"


def _provider_for_settings(provider_repo: Any, provider_id: str) -> Any | None:
    if provider_repo is None or not provider_id.isdigit():
        return None
    return provider_repo.get(int(provider_id))


def _remote_ready(provider: Any | None, model: str) -> bool:
    return bool(
        provider
        and provider.enabled
        and provider.api_key
        and provider.base_url
        and any(
            str(candidate.get("id") or "").strip() == model
            and is_embedding_model(
                candidate,
                provider_name=provider.name,
                provider_api_key=getattr(provider, "api_key", None),
            )
            for candidate in provider.get_models()
        )
    )


def get_capability(settings_get: SettingsGet, provider_repo: Any = None) -> dict[str, Any]:
    """Return feature state and its independent embedding readiness checks."""
    selected_model = (settings_get(_EMBEDDING_MODEL_KEY) or "").strip()
    backend = (settings_get(_EMBEDDING_BACKEND_KEY) or "onnx").strip().lower()
    backend = backend if backend in {"onnx", "remote"} else "onnx"
    provider_id = (settings_get(_EMBEDDING_PROVIDER_ID_KEY) or "").strip()
    provider = _provider_for_settings(provider_repo, provider_id)
    deps_available = local_embedding_deps_available()
    model_downloaded = bool(selected_model and is_model_downloaded(selected_model))
    provider_ready = _remote_ready(provider, selected_model)
    prerequisites_ok = (
        provider_ready
        if backend == "remote"
        else embedding_prerequisites_ok_for_model(selected_model)
    )
    feature_enabled = _as_bool(settings_get(_FEATURE_ENABLED_KEY))
    return {
        "feature_enabled": feature_enabled,
        "selected_model": selected_model,
        "backend": backend,
        "provider_id": provider_id,
        "prerequisites_ok": prerequisites_ok,
        "usable": feature_enabled and prerequisites_ok,
        "checks": {
            "model_selected": bool(selected_model),
            "model_downloaded": model_downloaded,
            "deps_available": deps_available,
            "provider_ready": provider_ready,
        },
        "deps_install_hint": None if deps_available else LOCAL_EMBEDDING_INSTALL_HINT,
    }


def set_feature_enabled(
    settings_get: SettingsGet,
    settings_set: SettingsSet,
    *,
    enabled: bool,
    backend: str | None = None,
    model: str | None,
    provider_id: str | None = None,
    provider_repo: Any = None,
) -> None:
    """Enable only after model-specific prerequisites pass."""
    if not enabled:
        settings_set(_FEATURE_ENABLED_KEY, "false")
        if model is not None:
            settings_set(_EMBEDDING_MODEL_KEY, model.strip())
        if backend is not None:
            settings_set(_EMBEDDING_BACKEND_KEY, backend)
        if provider_id is not None:
            settings_set(_EMBEDDING_PROVIDER_ID_KEY, provider_id.strip())
        return
    selected_backend = (backend or "onnx").strip().lower()
    if selected_backend not in {"onnx", "remote"}:
        raise ValueError("knowledge embedding backend must be onnx or remote")
    selected_model = (model or "").strip()
    if not selected_model:
        raise ValueError("enabling knowledge bases requires an embedding model")
    if selected_backend == "remote":
        selected_provider_id = (provider_id or "").strip()
        if not _remote_ready(
            _provider_for_settings(provider_repo, selected_provider_id), selected_model
        ):
            raise ValueError("knowledge remote embedding provider is not ready")
        verified_model = selected_model
    else:
        selected_provider_id = ""
        verified_model = require_embedding_prerequisites_for_model(selected_model)
    settings_set(_EMBEDDING_BACKEND_KEY, selected_backend)
    settings_set(_EMBEDDING_MODEL_KEY, verified_model)
    settings_set(_EMBEDDING_PROVIDER_ID_KEY, selected_provider_id)
    settings_set(_FEATURE_ENABLED_KEY, "true")


def assert_knowledge_usable(settings_get: SettingsGet, provider_repo: Any = None) -> None:
    """Raise a distinguishable runtime error when the capability cannot be used."""
    capability = get_capability(settings_get, provider_repo)
    if not capability["feature_enabled"]:
        raise RuntimeError("knowledge feature is disabled")
    if not capability["prerequisites_ok"]:
        raise RuntimeError("knowledge embedding prerequisites are not satisfied")
