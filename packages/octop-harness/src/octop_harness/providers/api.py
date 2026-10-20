"""Serialize provider presets for HTTP dashboards and other consumers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from octop_harness.providers import ModelPreset, ProviderPreset


def serialize_model_preset(model: ModelPreset) -> dict[str, Any]:
    """Return a JSON-friendly model preset (includes ``input`` when non-text)."""
    entry: dict[str, Any] = {
        "id": model.id,
        "name": model.name,
        "max_input_tokens": model.max_input_tokens or None,
        "context_window": model.effective_context_window or None,
        "max_output_tokens": model.max_output_tokens or None,
    }
    if model.input != ("text",):
        entry["input"] = list(model.input)
    if model.reasoning:
        entry["reasoning"] = True
    return entry


def serialize_provider_preset(preset: ProviderPreset) -> dict[str, Any]:
    """Return a dashboard-ready provider preset dict."""
    entry: dict[str, Any] = {
        "id": preset.id,
        "name": preset.name,
        "base_url": preset.base_url,
        "protocol": preset.protocol,
        "api_key_prefix": preset.api_key_prefix,
        "models": [serialize_model_preset(m) for m in preset.models],
        "logo_id": _logo_id(preset),
    }
    if preset.vendor:
        entry["vendor"] = preset.vendor
        entry["provider_group"] = preset.vendor
    if preset.vendor_name:
        entry["vendor_name"] = preset.vendor_name
        entry["provider_group_name"] = preset.vendor_name
    if preset.variant:
        entry["variant"] = preset.variant
        entry["provider_variant"] = preset.variant
    return entry


def _logo_id(preset: ProviderPreset) -> str:
    if preset.logo:
        stem = preset.logo.rsplit(".", 1)[0]
        return stem
    return preset.id
