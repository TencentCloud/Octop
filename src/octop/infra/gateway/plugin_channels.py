"""Bridge plugin-contributed channels into the gateway's channel registry.

Plugins with ``kind: channel`` register their implementations through
``PluginContext.channel()`` at ``setup()`` time (see octop-harness). This
module applies those registrations to ``octop_gateway`` at boot / plugin
reload, so channels of that kind can be created, probed, persisted and
rebuilt exactly like builtin ones.

Design notes:

- Idempotent: applying twice is a no-op (the gateway's
  ``register_channel_kind`` keeps the first registration), so hosts can
  replay after every plugin reload.
- Plugin kinds never shadow builtin kinds; the gateway raises on clashes.
- Registered kinds are exposed to the API layer as plain strings; the
  dashboard receives them through the channel-catalogue endpoint.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PluginChannelInfo:
    """Display-facing summary of one plugin-contributed channel kind."""

    kind: str
    label: str
    icon: str
    intro_url: str
    fields: list[dict[str, Any]]
    plugin_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "icon": self.icon,
            "intro_url": self.intro_url,
            "fields": self.fields,
            "plugin_id": self.plugin_id,
        }


def apply_plugin_channels(
    *,
    registry: Any,
    register: Any | None = None,
) -> list[PluginChannelInfo]:
    """Apply every channel registration from loaded plugins to the gateway.

    Args:
        registry: The harness ``PluginRegistry`` singleton (or any object
            exposing ``all_channels()`` returning ``ChannelRegistration``s).
        register: The gateway registration callable; defaults to
            ``octop_gateway.channels.register_channel_kind``. Injectable so
            hosts (and tests) can target a different registry.

    Returns:
        Summaries of the channel kinds that are registered and usable,
        sorted by kind for stable UI ordering.
    """
    if register is None:  # pragma: no cover - exercised via real gateway
        from octop_gateway.channels import register_channel_kind as register

    applied: list[PluginChannelInfo] = []
    seen: set[str] = set()
    for reg in registry.all_channels():
        if reg.kind in seen:
            continue
        seen.add(reg.kind)
        try:
            register(reg.kind, reg.channel_cls)
        except Exception:
            logger.exception(
                "plugin %s: failed to register channel kind %r; skipping",
                reg.plugin_id,
                reg.kind,
            )
            continue
        applied.append(
            PluginChannelInfo(
                kind=reg.kind,
                label=reg.label or reg.kind,
                icon=reg.icon,
                intro_url=reg.intro_url,
                fields=list(reg.fields or []),
                plugin_id=reg.plugin_id,
            ),
        )
    applied.sort(key=lambda info: info.kind)
    if applied:
        logger.info(
            "applied %d plugin channel kind(s): %s",
            len(applied),
            ", ".join(info.kind for info in applied),
        )
    return applied


def plugin_channel_kinds(
    *,
    registry: Any | None = None,
) -> list[PluginChannelInfo]:
    """Currently registered plugin channel kinds (for the dashboard catalogue).

    Reads the harness ``PluginRegistry`` — the same source
    :func:`apply_plugin_channels` applied at boot/reload — so the returned
    list always matches what the gateway can actually build right now.

    Args:
        registry: Optional harness ``PluginRegistry`` override (defaults to
            the process-global singleton).
    """
    if registry is None:  # pragma: no cover - default singleton path
        from octop_harness.plugins.registry import PluginRegistry

        registry = PluginRegistry()

    return _summarize(registry.all_channels())


def _summarize(regs: list[Any]) -> list[PluginChannelInfo]:
    out: list[PluginChannelInfo] = []
    seen: set[str] = set()
    for reg in regs:
        if reg.kind in seen:
            continue
        seen.add(reg.kind)
        out.append(
            PluginChannelInfo(
                kind=reg.kind,
                label=reg.label or reg.kind,
                icon=reg.icon,
                intro_url=reg.intro_url,
                fields=list(reg.fields or []),
                plugin_id=reg.plugin_id,
            ),
        )
    out.sort(key=lambda info: info.kind)
    return out
