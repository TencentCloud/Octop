"""Flags on provider ``models_json`` entries that affect chat / auto-routing."""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlparse

# LocalServiceCard creates the ONNX provider with ``api_key=preset.id`` ("onnx").
_ONNX_PRESET_API_KEY = "onnx"
# Exact display / id names from the onnx preset — never substring "local"/"onnx".
_ONNX_PRESET_NAMES = frozenset({"onnx", "onnx (local)"})
# Same pattern for Ollama (placeholder api_key + exact preset names).
_OLLAMA_PRESET_API_KEY = "ollama"
_OLLAMA_PRESET_NAMES = frozenset({"ollama", "ollama (local)"})
# Well-known local hostnames (including the docker service name ``ollama``) and
# suffixes that never point at a public Ollama cloud endpoint.
_LOCAL_OLLAMA_HOSTNAMES = frozenset(
    {"localhost", "ollama", "host.docker.internal", "gateway.docker.internal"}
)
_LOCAL_OLLAMA_HOST_SUFFIXES = (".local", ".localhost", ".internal")


def is_onnx_local_provider(
    provider_name: str | None = None,
    *,
    provider_api_key: str | None = None,
) -> bool:
    """True when this row is the local ONNX embedding preset.

    Prefer the stable placeholder API key written at create time. Fall back to
    exact preset name/id matches only — Ollama is also "local" and must not match.
    """
    if provider_api_key is not None and provider_api_key.strip().lower() == _ONNX_PRESET_API_KEY:
        return True
    if not provider_name:
        return False
    return provider_name.strip().lower() in _ONNX_PRESET_NAMES


def _is_local_ollama_url(url: str) -> bool:
    """True when *url* targets a local Ollama runtime, not a cloud endpoint.

    ``https://ollama.com/v1`` is the official *cloud* service and must not be
    treated as local just because its hostname contains "ollama". Only match
    when the URL really points at this machine: the default port 11434, a
    loopback / private / link-local address, or a well-known local hostname.
    """
    url = (url or "").strip().lower()
    if not url:
        return False
    # Default Ollama port is a strong local signal regardless of the host.
    if "11434" in url:
        return True
    # Parse the host, tolerating scheme-less values like "ollama" or "localhost".
    try:
        parsed = urlparse(url if "://" in url else f"//{url}")
    except ValueError:
        parsed = None
    host = (parsed.hostname or "").lower() if parsed is not None else ""
    if not host:
        return False
    if host in _LOCAL_OLLAMA_HOSTNAMES:
        return True
    if host.endswith(_LOCAL_OLLAMA_HOST_SUFFIXES):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def is_ollama_local_provider(
    provider_name: str | None = None,
    *,
    provider_api_key: str | None = None,
    provider_base_url: str | None = None,
) -> bool:
    """True when this row is the local Ollama preset.

    Prefer the stable placeholder API key, then exact preset names. Base URL
    hints match the dashboard (port 11434 / host ``ollama``) so delete
    protection stays aligned with the hidden UI button.
    """
    if is_onnx_local_provider(provider_name, provider_api_key=provider_api_key):
        return False
    if provider_api_key is not None and provider_api_key.strip().lower() == _OLLAMA_PRESET_API_KEY:
        return True
    if provider_name and provider_name.strip().lower() in _OLLAMA_PRESET_NAMES:
        return True
    return _is_local_ollama_url(provider_base_url or "")


def is_local_runtime_provider(
    provider_name: str | None = None,
    *,
    provider_api_key: str | None = None,
    provider_base_url: str | None = None,
) -> bool:
    """True for onboard local runtimes (ONNX / Ollama) that must not be deleted."""
    return is_onnx_local_provider(
        provider_name, provider_api_key=provider_api_key
    ) or is_ollama_local_provider(
        provider_name,
        provider_api_key=provider_api_key,
        provider_base_url=provider_base_url,
    )


def is_embedding_model(
    model: dict[str, Any],
    *,
    provider_name: str | None = None,
    provider_api_key: str | None = None,
) -> bool:
    """True when *model* is embedding-only (not for chat / auto-route).

    Explicit flags win:
    - ``embedding: true``
    - ``task: "embedding"``

    Legacy fallback: models under the ONNX local provider are treated as
    embedding-only even if the flag was missing.
    """
    if model.get("embedding") is True:
        return True
    task = str(model.get("task") or "").strip().lower()
    if task == "embedding":
        return True
    return is_onnx_local_provider(provider_name, provider_api_key=provider_api_key)


def is_vision_model(model: dict[str, Any]) -> bool:
    """True when a model entry declares or conventionally supports image input."""
    model_id = str(model.get("id") or "").strip().lower()
    raw_input = model.get("input")
    if isinstance(raw_input, list) and any(
        str(modality).strip().lower() == "image" for modality in raw_input
    ):
        return True
    return any(
        hint in model_id
        for hint in (
            "-vl",
            "vision",
            "-image",
            "gpt-4o",
            "gpt-4.1",
            "claude-3",
            "gemini",
        )
    )


def is_chat_eligible_model(
    model: dict[str, Any],
    *,
    provider_name: str | None = None,
    provider_api_key: str | None = None,
) -> bool:
    """True when *model* may appear in chat pickers and auto-route candidates."""
    if not model.get("enabled", True):
        return False
    if is_embedding_model(model, provider_name=provider_name, provider_api_key=provider_api_key):
        return False
    return bool(str(model.get("id") or "").strip())
