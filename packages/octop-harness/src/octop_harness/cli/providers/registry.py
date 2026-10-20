"""Provider preset registry — re-exports core types from octop_harness.providers."""

from __future__ import annotations

from octop_harness.providers import (
    ModelPreset,
    ProviderPreset,
    load_provider_templates,
)


def _build_registry() -> dict[str, ProviderPreset]:
    """Build provider preset registry from JSON template."""
    presets = load_provider_templates()
    return {p.id: p for p in presets}


PROVIDER_PRESETS: dict[str, ProviderPreset] = _build_registry()


def get_preset(provider_id: str) -> ProviderPreset | None:
    """Return the preset for *provider_id*, or ``None`` if unknown."""
    return PROVIDER_PRESETS.get(provider_id)


def list_presets() -> list[ProviderPreset]:
    """Return all available provider presets."""
    return list(PROVIDER_PRESETS.values())


__all__ = [
    "PROVIDER_PRESETS",
    "ModelPreset",
    "ProviderPreset",
    "get_preset",
    "list_presets",
]
