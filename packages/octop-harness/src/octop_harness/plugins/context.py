"""Plugin registration context passed to ``setup()``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from octop_harness.plugins.manifest import PluginManifest
from octop_harness.plugins.registry import (
    ChannelRegistration,
    LoadedPlugin,
    MiddlewareRegistration,
    PluginRegistry,
    ToolRegistration,
)


class PluginContext:
    """API surface for plugin authors inside ``setup(ctx)``."""

    def __init__(self, *, manifest: PluginManifest, source_path: Path) -> None:
        self._manifest = manifest
        self._source_path = source_path
        self._tools: list[ToolRegistration] = []
        self._middleware: list[MiddlewareRegistration] = []
        self._channels: list[ChannelRegistration] = []
        self._skills_dir: Path | None = None
        self._model_factory: Any | None = None
        self._get_protocol: Any | None = None

    @property
    def plugin_id(self) -> str:
        return self._manifest.id

    @property
    def source_path(self) -> Path:
        return self._source_path

    def tool(
        self,
        name: str,
        fn: Any,
        *,
        description: str = "",
        config_fields: list[dict[str, Any]] | None = None,
    ) -> None:
        if self._manifest.kind != "tool":
            raise ValueError(f"plugin {self._manifest.id!r} is kind={self._manifest.kind!r}, not tool")
        tool_name = str(name).strip()
        if not tool_name:
            raise ValueError("tool name must not be empty")
        self._tools.append(
            ToolRegistration(
                plugin_id=self._manifest.id,
                name=tool_name,
                fn=fn,
                description=description or tool_name,
                config_fields=list(config_fields or []),
            ),
        )

    def middleware(self, instance: Any, *, priority: int = 100) -> None:
        if self._manifest.kind != "hook":
            raise ValueError(f"plugin {self._manifest.id!r} is kind={self._manifest.kind!r}, not hook")
        self._middleware.append(
            MiddlewareRegistration(
                plugin_id=self._manifest.id,
                instance=instance,
                priority=priority,
            ),
        )

    def channel(
        self,
        kind: str,
        channel_cls: Any,
        *,
        label: str = "",
        icon: str = "",
        intro_url: str = "",
        fields: list[dict[str, Any]] | None = None,
    ) -> None:
        """Register a channel implementation contributed by this plugin.

        Args:
            kind: Channel-type string persisted in the control-plane DB and
                passed to the gateway channel manager (e.g. ``"acme"``).
            channel_cls: Channel class inheriting the hosts BaseChannel. The
                host application is responsible for constructing it with its
                own ``ChannelConfig`` contract.
            label: Display name for the dashboard channel catalogue. Falls
                back to ``kind`` when omitted.
            icon: Optional icon URL / asset path for the catalogue card.
            intro_url: Optional "how to get credentials" link.
            fields: Optional form schema (list of ``ChannelField``-shaped
                dicts: ``name``/``label``/``type``/``placeholder``/
                ``required``/``helpKey``). When omitted the dashboard falls
                back to a raw-JSON config textarea.
        """
        if self._manifest.kind != "channel":
            raise ValueError(f"plugin {self._manifest.id!r} is kind={self._manifest.kind!r}, not channel")
        normalized_label = str(label or "").strip() or str(kind).strip()
        self._channels.append(
            ChannelRegistration(
                plugin_id=self._manifest.id,
                kind=str(kind),
                channel_cls=channel_cls,
                label=normalized_label,
                icon=str(icon or "").strip(),
                intro_url=str(intro_url or "").strip(),
                fields=list(fields or []),
            ),
        )

    def skills(self, relative_path: str) -> None:
        if self._manifest.kind != "skill":
            raise ValueError(f"plugin {self._manifest.id!r} is kind={self._manifest.kind!r}, not skill")
        skills_dir = (self._source_path / relative_path).resolve()
        if not skills_dir.is_dir():
            raise FileNotFoundError(f"skills directory not found: {skills_dir}")
        self._skills_dir = skills_dir

    @property
    def model_factory(self) -> Any | None:
        """Agent-bound model factory; ``None`` during ``setup()`` before bind."""
        return self._model_factory

    @property
    def get_protocol(self) -> Any | None:
        """Protocol resolver paired with :attr:`model_factory`."""
        return self._get_protocol

    def bind_model_factory(
        self,
        factory: Any,
        *,
        get_protocol: Any | None = None,
    ) -> None:
        self._model_factory = factory
        self._get_protocol = get_protocol

    def get_model_access(self, spec: Any, **kwargs: Any) -> Any:
        """Resolve *spec* to a :class:`ModelAccess` using the bound protocol."""
        if self._model_factory is None:
            raise RuntimeError("model_factory is not bound yet")
        return self._model_factory.get_for(
            spec,
            get_protocol=self._get_protocol,
            **kwargs,
        )

    def to_loaded(self) -> LoadedPlugin:
        return LoadedPlugin(
            manifest=self._manifest,
            source_path=self._source_path,
            tools=list(self._tools),
            middleware=list(self._middleware),
            channels=list(self._channels),
            skills_dir=self._skills_dir,
        )


def register_loaded(ctx: PluginContext) -> LoadedPlugin:
    loaded = ctx.to_loaded()
    loaded.context = ctx
    PluginRegistry().register(loaded)
    return loaded
