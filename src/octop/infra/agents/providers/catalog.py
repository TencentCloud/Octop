"""Keep provider packages scoped to their own bundled model catalogs."""

from __future__ import annotations

import json
from typing import Any

from octop.infra.agents.providers.presets import load_provider_presets


def package_preset(
    name: str,
    *,
    preset_id: str | None = None,
    extra_json: str | None = None,
) -> dict[str, Any] | None:
    """Match a package by identity, never by a URL shared with other plans."""
    if not preset_id and isinstance(extra_json, str):
        try:
            extra = json.loads(extra_json)
        except ValueError:
            extra = None
        if isinstance(extra, dict) and isinstance(extra.get("preset_id"), str):
            preset_id = extra["preset_id"]
    # Custom providers keep their remote discovery behavior.
    if not preset_id and not name.lower().startswith(("tencent-", "tencent cloud")):
        return None
    presets = [p for p in load_provider_presets() if p.get("model_catalog_locked")]
    if preset_id:
        match = next((p for p in presets if p["id"] == preset_id), None)
        if match is not None:
            return match
    return next((p for p in presets if name in {p["id"], p["name"]}), None)


def package_models(
    models: list[dict[str, Any]],
    preset: dict[str, Any] | None,
    *,
    display_order: bool = False,
) -> list[dict[str, Any]]:
    """Retain user metadata and enabled states, excluding other packages' ids."""
    if preset is None:
        return models
    ranks = {model["id"]: index for index, model in enumerate(preset["models"])}
    own = [model for model in models if model.get("id") in ranks]
    if display_order:
        own.sort(key=lambda model: ranks[model["id"]])
    return own


def provider_models(row: Any, *, display_order: bool = False) -> list[dict[str, Any]]:
    """Use the same package boundary for API output and runtime routing."""
    models: list[dict[str, Any]] = row.get_models()
    preset = package_preset(
        str(getattr(row, "name", "")),
        extra_json=getattr(row, "extra_json", None),
    )
    return package_models(models, preset, display_order=display_order)


def with_default_first(models: list[dict[str, Any]], model_id: str | None) -> list[dict[str, Any]]:
    """Storage order retains the chosen default independently of display order."""
    if not model_id or not any(model.get("id") == model_id for model in models):
        return models
    return [model for model in models if model.get("id") == model_id] + [
        model for model in models if model.get("id") != model_id
    ]
