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
_KIND_ERRORS: dict[str, tuple[str, str]] = {}
_CURRENT_ERRORS: dict[str, str] = {}


def current_registration_errors() -> dict[str, str]:
    return dict(_CURRENT_ERRORS)


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
        kind
        for kind in _CLASSES.keys() | desired.keys() | _APPLIED.keys()
        if _CLASSES.get(kind) != desired.get(kind) or (kind in _APPLIED and kind not in desired)
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
    from octop_gateway import channels as gateway_channels

    if register is None:
        register = getattr(gateway_channels, "register_channel_kind", None)
    if unregister is None:
        unregister = getattr(gateway_channels, "unregister_channel_kind", None)
    all_channels = getattr(registry, "all_channels", None)
    desired: dict[str, Any] = {}
    for reg in all_channels() if callable(all_channels) else []:
        desired.setdefault(reg.kind, reg)
    changed = changed_plugin_channel_kinds(registry)
    _CURRENT_ERRORS.clear()
    blocked: set[str] = set()
    for kind in changed:
        old = _APPLIED.get(kind)
        reg = desired.get(kind)
        if old is not None:
            try:
                if not callable(unregister):
                    raise RuntimeError(
                        "gateway lacks channel plugin lifecycle support; upgrade gateway"
                    )
                unregister(kind, plugin_id=old.plugin_id)
            except Exception as exc:
                message = f"channel {kind}: {exc}"
                # Retrying an unchanged removal must not fail unrelated mutations.
                if kind not in _KIND_ERRORS or _CLASSES.get(kind) != (
                    (reg.plugin_id, reg.channel_cls) if reg is not None else None
                ):
                    _CURRENT_ERRORS[old.plugin_id] = message
                _KIND_ERRORS[kind] = (old.plugin_id, message)
                # Remember the attempted class, but preserve the live registration.
                if reg is not None:
                    _CLASSES[kind] = (reg.plugin_id, reg.channel_cls)
                else:
                    _CLASSES.pop(kind, None)
                blocked.add(kind)
                continue
        _APPLIED.pop(kind, None)
        _CLASSES.pop(kind, None)
        _KIND_ERRORS.pop(kind, None)
    for kind, reg in desired.items():
        if kind in blocked:
            continue
        signature = (reg.plugin_id, reg.channel_cls)
        if kind in _KIND_ERRORS and _CLASSES.get(kind) == signature:
            continue
        try:
            if kind in changed or kind not in _APPLIED:
                if not callable(register) or not callable(unregister):
                    raise RuntimeError(
                        "gateway lacks channel plugin lifecycle support; upgrade gateway"
                    )
                register(kind, reg.channel_cls, plugin_id=reg.plugin_id)
            _CLASSES[kind] = signature
        except Exception as exc:
            _CLASSES[kind] = signature
            message = f"channel {kind}: {exc}"
            _KIND_ERRORS[kind] = (reg.plugin_id, message)
            _CURRENT_ERRORS[reg.plugin_id] = message
            logger.exception("plugin %s: failed channel %s", reg.plugin_id, kind)
            continue
        _APPLIED[kind] = PluginChannelInfo(
            kind=kind,
            label=reg.label or kind,
            icon=reg.icon,
            intro_url=reg.intro_url,
            fields=list(reg.fields or []),
            plugin_id=reg.plugin_id,
        )
    _ERRORS.clear()
    for owner, message in _KIND_ERRORS.values():
        _ERRORS[owner] = message
    applied = [
        info for kind, info in _APPLIED.items() if kind in desired and kind not in _KIND_ERRORS
    ]
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
