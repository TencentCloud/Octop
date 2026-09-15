"""Flags on provider ``models_json`` entries that affect chat / auto-routing."""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlsplit

# LocalServiceCard creates the ONNX provider with ``api_key=preset.id`` ("onnx").
_ONNX_PRESET_API_KEY = "onnx"
# Exact display / id names from the onnx preset — never substring "local"/"onnx".
_ONNX_PRESET_NAMES = frozenset({"onnx", "onnx (local)"})
# Same pattern for Ollama (placeholder api_key + exact preset names).
_OLLAMA_PRESET_API_KEY = "ollama"
_OLLAMA_PRESET_NAMES = frozenset({"ollama", "ollama (local)"})
# Hosts that always mean "this machine" (docker service name, container
# hostnames, loopback aliases). Public names such as ``ollama.com`` are
# deliberately absent: every official Ollama host contains "ollama".
_LOCAL_HOSTS = frozenset({"localhost", "ollama", "host.docker.internal", "gateway.docker.internal"})
# Suffixes reserved for local naming (mDNS, localhost subdomains, internal nets).
_LOCAL_HOST_SUFFIXES = (".local", ".localhost", ".internal")


def _base_url_is_local_machine(raw_url: str) -> bool:
    """True when a provider base URL points at this machine.

    Port 11434, loopback / private / link-local IPs, well-known local host
    names and local suffixes all count. Anything else — including public
    domains that merely contain "ollama" (e.g. ``https://ollama.com/v1``) —
    does not. Mirrors the dashboard ``hostLooksLocal`` rule.
    """
    url = raw_url.strip().lower()
    if not url:
        return False
    try:
        parts = urlsplit(url if "://" in url else f"http://{url}")
    except ValueError:
        return False
    host = (parts.hostname or "").rstrip(".")
    if not host:
        return "11434" in url
    if parts.port == 11434:
        return True
    if host in _LOCAL_HOSTS or host.endswith(_LOCAL_HOST_SUFFIXES):
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return addr.is_loopback or addr.is_private or addr.is_link_local


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


def is_ollama_local_provider(
    provider_name: str | None = None,
    *,
    provider_api_key: str | None = None,
    provider_base_url: str | None = None,
) -> bool:
    """True when this row is the local Ollama preset.

    Prefer the stable placeholder API key, then exact preset names. Base URL
    hints match the dashboard (this-machine hosts only) so delete protection
    stays aligned with the hidden UI button. In particular a cloud endpoint
    such as ``https://ollama.com/v1`` is *not* local.
    """
    if is_onnx_local_provider(provider_name, provider_api_key=provider_api_key):
        return False
    if provider_api_key is not None and provider_api_key.strip().lower() == _OLLAMA_PRESET_API_KEY:
        return True
    if provider_name and provider_name.strip().lower() in _OLLAMA_PRESET_NAMES:
        return True
    return _base_url_is_local_machine(provider_base_url or "")


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
