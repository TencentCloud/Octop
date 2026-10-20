"""In-process plugin registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from octop_harness.plugins.manifest import PluginManifest

ConfigField = dict[str, Any]
ToolFn = Callable[..., Any]


@dataclass
class ToolRegistration:
    plugin_id: str
    name: str
    fn: ToolFn
    description: str
    config_fields: list[ConfigField] = field(default_factory=list)


@dataclass
class MiddlewareRegistration:
    plugin_id: str
    instance: Any
    priority: int = 100


@dataclass
class SkillRegistration:
    plugin_id: str
    skills_dir: Path


@dataclass
class ChannelRegistration:
    """A channel class contributed by a plugin.

    ``kind`` is the channel-type string persisted in the control-plane
    database (e.g. ``"octo"``) and passed to the gateway's channel manager.
    ``label`` / ``icon`` / ``intro_url`` are display hints for the dashboard
    channel catalogue; ``fields`` is an optional form schema (same shape as
    the dashboard's ``ChannelField`` dicts) so the drawer can render real
    inputs instead of the raw-JSON fallback.
    """

    plugin_id: str
    kind: str
    channel_cls: Any
    label: str = ""
    icon: str = ""
    intro_url: str = ""
    fields: list[ConfigField] = field(default_factory=list)

    def __post_init__(self) -> None:
        kind = str(self.kind).strip().lower()
        if not kind:
            raise ValueError("channel kind must not be empty")
        self.kind = kind
        if not isinstance(self.channel_cls, type):
            raise ValueError("channel_cls must be a class")
        if self.fields and not isinstance(self.fields, list):
            raise ValueError("fields must be a list of field dicts")


@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    source_path: Path
    tools: list[ToolRegistration] = field(default_factory=list)
    middleware: list[MiddlewareRegistration] = field(default_factory=list)
    channels: list[ChannelRegistration] = field(default_factory=list)
    skills_dir: Path | None = None
    diagnostics: list[str] = field(default_factory=list)
    context: Any | None = None


class PluginRegistry:
    """Global registry of loaded plugins."""

    _instance: PluginRegistry | None = None
    _plugins: dict[str, LoadedPlugin]

    def __new__(cls) -> PluginRegistry:
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._plugins = {}
            cls._instance = inst
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def clear(self) -> None:
        self._plugins.clear()

    def register(self, loaded: LoadedPlugin) -> None:
        if any(reg.plugin_id != loaded.manifest.id for reg in loaded.channels):
            raise ValueError("channel registration owner must match plugin ID")
        kinds = [reg.kind for reg in loaded.channels]
        if len(kinds) != len(set(kinds)):
            raise ValueError("duplicate channel kind in plugin")
        for plugin in self._plugins.values():
            if plugin.manifest.id == loaded.manifest.id:
                continue
            if set(kinds).intersection(reg.kind for reg in plugin.channels):
                raise ValueError("channel kind is already owned by another plugin")
        self._plugins[loaded.manifest.id] = loaded

    def unregister(self, plugin_id: str) -> LoadedPlugin | None:
        return self._plugins.pop(plugin_id, None)

    def get(self, plugin_id: str) -> LoadedPlugin | None:
        return self._plugins.get(plugin_id)

    def list_plugins(self) -> list[LoadedPlugin]:
        return list(self._plugins.values())

    def all_loaded(self) -> list[LoadedPlugin]:
        return self.list_plugins()

    def all_tools(self) -> list[ToolRegistration]:
        out: list[ToolRegistration] = []
        for plugin in self._plugins.values():
            out.extend(plugin.tools)
        return out

    def all_channels(self) -> list[ChannelRegistration]:
        """Channel registrations from loaded plugins; register() rejects conflicting owners."""
        out: list[ChannelRegistration] = []
        seen: set[str] = set()
        for plugin in self._plugins.values():
            if plugin.manifest.kind != "channel":
                continue
            for reg in plugin.channels:
                if reg.kind in seen:
                    continue
                seen.add(reg.kind)
                out.append(reg)
        return out

    def build_middleware_chain(self, *, global_enabled: dict[str, bool] | None = None) -> list[Any]:
        """Return middleware instances sorted by priority (lower runs earlier)."""
        enabled = global_enabled or {}
        entries: list[MiddlewareRegistration] = []
        for plugin in self._plugins.values():
            if enabled.get(plugin.manifest.id) is False:
                continue
            entries.extend(plugin.middleware)
        entries.sort(key=lambda e: e.priority)
        return [e.instance for e in entries]
