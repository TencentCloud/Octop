"""System configuration a plugin carries in ``plugin.yaml`` (the ``config`` capability).

A plugin that lists ``config`` in ``capabilities`` may ship, without code:

``config.provider_presets``
    Model provider presets in the bundled preset shape. Shown first in the
    provider picker; an id Octop already ships is ignored.
``config.providers``
    Providers to create from a preset (``{preset, name}``) when no provider
    with that name exists. No API key is stored; an admin fills it in.
``config.default_model``
    ``provider/model`` set as the instance default when none is configured.
``config.settings``
    Values for a short allowlist of ``config.json`` keys.

The plugin supplies defaults and the admin has the last word. Each part is
applied once per plugin version: a setting is written only while it still
holds Octop's built-in default, a provider only if the name is free, and the
default model only if none is set. Uninstalling a plugin reverts nothing.
``config.json`` settings take effect when the process (re)starts, the same
as edits on the admin config page; presets, providers and the default model
take effect at once.
"""

from __future__ import annotations

import copy
import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

from octop.config import OctopConfig
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.json_file import read_json_object, write_json_atomic

logger = logging.getLogger(__name__)

CONFIG_CAPABILITY = "config"

# config.json keys a plugin may give a default for. Database, TLS, sign-in
# security, tokens, and network binding stay with the admin.
SETTING_TYPES: Mapping[str, type] = {
    "default_timezone": str,
    "max_upload_mb": int,
    "browser_idle_timeout_minutes": int,
    "public_base_url": str,
}

_SETTINGS_MARK = "config_settings_applied"
_MODELS_MARK = "config_models_applied"


@dataclass(frozen=True)
class ProviderSpec:
    preset: str
    name: str


@dataclass(frozen=True)
class PluginConfig:
    plugin_id: str
    version: str
    provider_presets: tuple[dict[str, Any], ...] = ()
    providers: tuple[ProviderSpec, ...] = ()
    default_model: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        """What the plugin configures, for the API and the dashboard."""
        return {
            "provider_presets": [str(p["id"]) for p in self.provider_presets],
            "providers": [spec.name for spec in self.providers],
            "default_model": self.default_model,
            "settings": dict(self.settings),
        }


def _invalid(plugin_id: str, detail: str) -> OctopError:
    return OctopError(
        ErrorCode.PLUGIN_INVALID_ARCHIVE,
        f"plugin {plugin_id!r}: invalid config: {detail}",
    )


def parse_plugin_config(plugin_dir: Path) -> PluginConfig | None:
    """Read and validate ``config``; ``None`` when the plugin does not declare the capability."""
    raw = yaml.safe_load((plugin_dir / "plugin.yaml").read_text(encoding="utf-8"))
    data = raw if isinstance(raw, dict) else {}
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list) or CONFIG_CAPABILITY not in [
        str(c).strip().lower() for c in capabilities
    ]:
        return None
    plugin_id = str(data.get("id") or plugin_dir.name).strip()
    version = str(data.get("version") or "").strip()
    section = data.get("config")
    if not isinstance(section, dict) or not section:
        raise _invalid(plugin_id, "`config` must be a non-empty mapping")
    unknown = sorted(set(section) - {"provider_presets", "providers", "default_model", "settings"})
    if unknown:
        raise _invalid(plugin_id, f"unknown keys: {', '.join(unknown)}")

    presets: list[dict[str, Any]] = []
    for item in section.get("provider_presets") or []:
        if not isinstance(item, dict) or not str(item.get("id") or "").strip():
            raise _invalid(plugin_id, "each provider preset needs an id")
        if not isinstance(item.get("models", []), list):
            raise _invalid(plugin_id, f"preset {item['id']!r}: models must be a list")
        presets.append(copy.deepcopy(item))

    providers: list[ProviderSpec] = []
    for item in section.get("providers") or []:
        if not isinstance(item, dict):
            raise _invalid(plugin_id, "each provider must be a mapping")
        preset = str(item.get("preset") or "").strip()
        name = str(item.get("name") or preset).strip()
        if not preset or not name:
            raise _invalid(plugin_id, "each provider needs a preset")
        providers.append(ProviderSpec(preset=preset, name=name))

    default_model = section.get("default_model")
    if default_model is not None:
        default_model = str(default_model).strip()
        name, _, model = default_model.partition("/")
        if not name or not model:
            raise _invalid(plugin_id, "default_model must look like provider/model")

    settings: dict[str, Any] = {}
    raw_settings = section.get("settings") or {}
    if not isinstance(raw_settings, dict):
        raise _invalid(plugin_id, "settings must be a mapping")
    for key, value in raw_settings.items():
        expected = SETTING_TYPES.get(str(key))
        if expected is None:
            raise _invalid(plugin_id, f"setting {key!r} cannot be set by a plugin")
        if not isinstance(value, expected) or isinstance(value, bool):
            raise _invalid(plugin_id, f"setting {key!r} must be {expected.__name__}")
        settings[str(key)] = value

    return PluginConfig(
        plugin_id=plugin_id,
        version=version,
        provider_presets=tuple(presets),
        providers=tuple(providers),
        default_model=default_model,
        settings=settings,
    )


# ── provider presets from enabled plugins ────────────────────────────────────

_PLUGIN_PRESETS: dict[str, tuple[dict[str, Any], ...]] = {}


def replace_plugin_presets(by_plugin: Mapping[str, Iterable[dict[str, Any]]]) -> None:
    """Replace the published presets with those of the plugins in ``by_plugin``."""
    _PLUGIN_PRESETS.clear()
    for plugin_id, presets in by_plugin.items():
        items = tuple(copy.deepcopy(dict(p)) for p in presets)
        if items:
            _PLUGIN_PRESETS[plugin_id] = items


def plugin_provider_presets() -> list[dict[str, Any]]:
    """Presets from loaded plugins, in plugin id order."""
    return [copy.deepcopy(p) for pid in sorted(_PLUGIN_PRESETS) for p in _PLUGIN_PRESETS[pid]]


# ── applying ─────────────────────────────────────────────────────────────────


def _plugin_entry(raw: dict[str, Any], plugin_id: str) -> dict[str, Any]:
    plugins = raw.setdefault("plugins", {})
    entry = plugins.get(plugin_id)
    if not isinstance(entry, dict):
        entry = {"enabled": bool(entry)} if isinstance(entry, bool) else {}
        plugins[plugin_id] = entry
    return entry


def apply_plugin_settings(config_path: Path, configs: Iterable[PluginConfig]) -> list[str]:
    """Write each plugin's setting defaults into ``config.json``, once per plugin version.

    A key is written only while it still holds Octop's built-in default.
    Returns ``plugin_id.key`` for every value written.
    """
    defaults = {f.name: f.default for f in fields(OctopConfig) if f.name in SETTING_TYPES}
    raw = read_json_object(config_path) or {}
    written: list[str] = []
    changed = False
    for cfg in configs:
        entry = _plugin_entry(raw, cfg.plugin_id)
        if not cfg.settings or entry.get(_SETTINGS_MARK) == cfg.version:
            continue
        for key, value in cfg.settings.items():
            if raw.get(key, defaults[key]) == defaults[key]:
                raw[key] = value
                written.append(f"{cfg.plugin_id}.{key}")
        entry[_SETTINGS_MARK] = cfg.version
        changed = True
    if changed:
        write_json_atomic(config_path, raw)
    if written:
        logger.info("plugin settings written to config.json: %s", ", ".join(written))
    return written


def apply_plugin_models(
    config_path: Path,
    configs: Iterable[PluginConfig],
    *,
    provider_repo: Any,
    settings_repo: Any,
    presets_by_id: Callable[[], Mapping[str, Mapping[str, Any]]],
) -> list[str]:
    """Create the plugins' providers and default model, once per plugin version.

    Returns the provider names created (and ``default_model`` when it was set).
    """
    raw = read_json_object(config_path) or {}
    done: list[str] = []
    changed = False
    presets: Mapping[str, Mapping[str, Any]] | None = None
    for cfg in configs:
        entry = _plugin_entry(raw, cfg.plugin_id)
        if not (cfg.providers or cfg.default_model) or entry.get(_MODELS_MARK) == cfg.version:
            continue
        if cfg.providers and presets is None:
            presets = presets_by_id()
        for spec in cfg.providers:
            if provider_repo.get_by_name(spec.name) is not None:
                continue
            preset = (presets or {}).get(spec.preset)
            if preset is None:
                logger.warning(
                    "plugin %s: provider preset %r not found", cfg.plugin_id, spec.preset
                )
                continue
            provider_repo.create(
                name=spec.name,
                kind=str(preset.get("protocol") or "openai"),
                base_url=str(preset.get("base_url") or "") or None,
                api_key=None,
                models_json=json.dumps(list(preset.get("models") or [])),
            )
            done.append(spec.name)
        if cfg.default_model:
            current_name, current_model = settings_repo.get_active_model()
            if not (current_name and current_model):
                name, _, model = cfg.default_model.partition("/")
                settings_repo.set_active_model(name, model)
                done.append("default_model")
        entry[_MODELS_MARK] = cfg.version
        changed = True
    if changed:
        write_json_atomic(config_path, raw)
    return done
