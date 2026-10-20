"""Built-in channel implementations."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from octop_gateway.channel import BaseChannel

# Lazy imports to avoid loading all platform SDKs at import time
_CHANNEL_MAP: dict[str, str] = {
    "discord": "octop_gateway.channels.discord",
    "feishu": "octop_gateway.channels.feishu",
    "dingtalk": "octop_gateway.channels.dingtalk",
    "qq": "octop_gateway.channels.qq",
    "wecom": "octop_gateway.channels.wecom",
    "weixin": "octop_gateway.channels.weixin",
    "yuanbao": "octop_gateway.channels.yuanbao",
    "xiaoyi": "octop_gateway.channels.xiaoyi",
    "mqtt": "octop_gateway.channels.mqtt",
    "telegram": "octop_gateway.channels.telegram",
}


class ChannelKind(StrEnum):
    """Canonical built-in channel kinds (mirrors :data:`_CHANNEL_MAP` keys).

    A parity test guards against drift; ``_CHANNEL_MAP`` remains the
    construction source of truth.
    """

    DISCORD = "discord"
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    QQ = "qq"
    WECOM = "wecom"
    WEIXIN = "weixin"
    YUANBAO = "yuanbao"
    XIAOYI = "xiaoyi"
    MQTT = "mqtt"
    TELEGRAM = "telegram"


#: All channel kinds that :class:`~octop_gateway.manager.ChannelManager` can build.
SUPPORTED_CHANNEL_KINDS: frozenset[str] = frozenset(_CHANNEL_MAP)

_CLASS_NAMES: dict[str, str] = {
    "discord": "DiscordChannel",
    "feishu": "FeishuChannel",
    "dingtalk": "DingTalkChannel",
    "qq": "QQChannel",
    "wecom": "WeComChannel",
    "weixin": "WeixinChannel",
    "yuanbao": "YuanbaoChannel",
    "xiaoyi": "XiaoyiChannel",
    "mqtt": "MQTTChannel",
    "telegram": "TelegramChannel",
}


def _load_channel(channel_id: str) -> type[BaseChannel]:
    """Lazily load a built-in channel class."""
    import importlib

    module_path = _CHANNEL_MAP[channel_id]
    class_name = _CLASS_NAMES[channel_id]
    module = importlib.import_module(module_path)
    return getattr(module, class_name)  # type: ignore[no-any-return]


class _LazyBuiltinDict(dict):  # type: ignore[type-arg]
    """Dict that lazily loads channel classes on first access."""

    def __init__(self) -> None:
        super().__init__()
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        import contextlib

        for cid in _CHANNEL_MAP:
            with contextlib.suppress(Exception):
                self[cid] = _load_channel(cid)

    def __getitem__(self, key: str) -> type[BaseChannel]:
        # If key is already loaded, return it directly
        if super().__contains__(key):
            return super().__getitem__(key)  # type: ignore[no-any-return]
        # If key is in channel map, try to lazily load it
        if key in _CHANNEL_MAP:
            self[key] = _load_channel(key)
            return super().__getitem__(key)  # type: ignore[no-any-return]
        # Key not in map, raise KeyError
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        # Return True if key is already loaded OR if it's in the channel map (can be loaded)
        if super().__contains__(key):
            return True
        return key in _CHANNEL_MAP

    def keys(self) -> Any:
        self._ensure_loaded()
        return super().keys()

    def values(self) -> Any:
        self._ensure_loaded()
        return super().values()

    def items(self) -> Any:
        self._ensure_loaded()
        return super().items()

    def __iter__(self) -> Any:
        self._ensure_loaded()
        return super().__iter__()

    def __len__(self) -> int:
        return len(_CHANNEL_MAP)


BUILTIN_CHANNELS: dict[str, type[BaseChannel]] = _LazyBuiltinDict()


_PLUGIN_OWNERS: dict[str, str] = {}


def registered_channel_kinds() -> frozenset[str]:
    """Return builtin and currently registered plugin kinds without loading SDKs."""
    return frozenset(_CHANNEL_MAP) | frozenset(_PLUGIN_OWNERS)


def register_channel_kind(kind: str, channel_cls: type[BaseChannel], *, plugin_id: str) -> None:
    """Register a BaseChannel subclass; the same owner may replace it on reload.

    Builtins and registrations owned by another plugin cannot be replaced.
    Hosts must stop affected live instances before replacing registrations.
    """
    from octop_gateway.channel import BaseChannel

    normalized = str(kind).strip().lower()
    owner = str(plugin_id).strip()
    if not owner:
        raise ValueError("plugin_id must not be empty")
    if not normalized:
        raise ValueError("channel kind must not be empty")
    if normalized in _CHANNEL_MAP:
        raise ValueError(f"channel kind {normalized!r} is a builtin kind and cannot be overridden")
    if not isinstance(channel_cls, type) or not issubclass(channel_cls, BaseChannel):
        raise TypeError("channel_cls must be a class inheriting BaseChannel")
    if normalized in BUILTIN_CHANNELS and _PLUGIN_OWNERS.get(normalized) != owner:
        raise ValueError(f"channel kind {normalized!r} is owned by another plugin")
    BUILTIN_CHANNELS[normalized] = channel_cls
    _PLUGIN_OWNERS[normalized] = owner


def unregister_channel_kind(kind: str, *, plugin_id: str) -> bool:
    """Remove only the matching owners registration; preserve builtin kinds."""
    owner = str(plugin_id).strip()
    if not owner:
        raise ValueError("plugin_id must not be empty")
    normalized = str(kind).strip().lower()
    if normalized in _CHANNEL_MAP:
        raise ValueError("cannot unregister a builtin channel kind")
    if normalized not in _PLUGIN_OWNERS:
        return False
    if _PLUGIN_OWNERS[normalized] != str(plugin_id).strip():
        raise ValueError(f"channel kind {normalized!r} is owned by another plugin")
    _PLUGIN_OWNERS.pop(normalized)
    BUILTIN_CHANNELS.pop(normalized, None)
    return True


__all__ = [
    "BUILTIN_CHANNELS",
    "SUPPORTED_CHANNEL_KINDS",
    "ChannelKind",
    "register_channel_kind",
    "registered_channel_kinds",
    "unregister_channel_kind",
]
