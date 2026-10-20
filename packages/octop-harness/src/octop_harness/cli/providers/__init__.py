"""Provider presets and setup wizard for the CLI."""

from __future__ import annotations

from octop_harness.cli.providers.registry import (
    PROVIDER_PRESETS,
    ModelPreset,
    ProviderPreset,
    get_preset,
    list_presets,
)

__all__ = [
    "PROVIDER_PRESETS",
    "ModelPreset",
    "ProviderPreset",
    "SetupResult",
    "get_preset",
    "list_presets",
    "run_setup_wizard",
]


def __getattr__(name: str) -> object:  # pragma: no cover
    if name in ("SetupResult", "run_setup_wizard"):
        from octop_harness.cli.providers.setup_wizard import SetupResult, run_setup_wizard

        _map = {
            "SetupResult": SetupResult,
            "run_setup_wizard": run_setup_wizard,
        }
        return _map[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
