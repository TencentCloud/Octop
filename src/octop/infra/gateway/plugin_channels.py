"""Bridge plugin-contributed channels into the gateway's channel registry.

Plugins with ``kind: channel`` register their implementations through
``PluginContext.channel()`` at ``setup()`` time (see octop-harness). This
module applies those registrations to ``octop_gateway`` at boot / plugin
reload, so channels of that kind can be created, probed, persisted and
rebuilt exactly like builtin ones.

Design notes:

Registrations are owned by plugin ID. Reconciliation removes previous entries
before applying the current registry. The host stops live plugin instances first.
Only successfully applied registrations enter the API catalogue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_APPLIED: dict[str, PluginChannelInfo] = {}
_CLASSES: dict[str, tuple[str, Any]] = {}
_ERRORS: dict[str, str] = {}


def registration_errors() -> dict[str, str]:
    return dict(_ERRORS)


def changed_plugin_channel_kinds(registry: Any) -> set[str]:
    all_channels = getattr(registry, "all_channels", None)
    desired = (
        {reg.kind: (reg.plugin_id, reg.channel_cls) for reg in all_channels()}
        if callable(all_channels)
        else {}
    )
    return {
        kind for kind in _CLASSES.keys() | desired.keys() if _CLASSES.get(kind) != desired.get(kind)
    }


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
    unregister: Any | None = None,
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

    if unregister is None:
        try:
            from octop_gateway.channels import unregister_channel_kind as unregister
        except ImportError:
            logger.warning(
                "gateway does not support plugin channel lifecycle; upgrade gateway first"
            )
            return []

    assert register is not None
    assert unregister is not None
    changed = changed_plugin_channel_kinds(registry)
    _ERRORS.clear()
    for kind in changed:
        old = _APPLIED.get(kind)
        if old is not None:
            try:
                unregister(kind, plugin_id=old.plugin_id)
            except Exception as exc:
                _ERRORS[old.plugin_id] = f"channel {kind}: {exc}"
                continue
        _APPLIED.pop(kind, None)
        _CLASSES.pop(kind, None)
    applied: list[PluginChannelInfo] = []
    seen: set[str] = set()
    all_channels = getattr(registry, "all_channels", None)
    for reg in all_channels() if callable(all_channels) else []:
        if reg.kind in seen:
            continue
        seen.add(reg.kind)
        if reg.plugin_id in _ERRORS:
            continue
        try:
            if reg.kind in changed or reg.kind not in _APPLIED:
                register(reg.kind, reg.channel_cls, plugin_id=reg.plugin_id)
            _CLASSES[reg.kind] = (reg.plugin_id, reg.channel_cls)
        except Exception as exc:
            _ERRORS[reg.plugin_id] = f"channel {reg.kind}: {exc}"
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
    _APPLIED.update({info.kind: info for info in applied})
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

    all_channels = getattr(registry, "all_channels", None)
    if not callable(all_channels):
        return []
    return [info for info in _summarize(all_channels()) if _APPLIED.get(info.kind) == info]


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
