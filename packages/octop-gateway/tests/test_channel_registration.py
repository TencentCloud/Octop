"""Tests for runtime channel-kind registration (plugin extension point)."""

from __future__ import annotations

import pytest

from octop_gateway.channel import BaseChannel, ChannelConfig, MessageProcessor
from octop_gateway.channels import (
    _PLUGIN_OWNERS,
    BUILTIN_CHANNELS,
    register_channel_kind,
    registered_channel_kinds,
    unregister_channel_kind,
)


class _StubChannel(BaseChannel):
    """Minimal channel implementation for registration tests."""

    channel_type = "acme"

    class Config(ChannelConfig):
        token: str = ""

    def __init__(self, processor: MessageProcessor, config: ChannelConfig | None = None) -> None:
        super().__init__(processor, config=config)


@pytest.fixture(autouse=True)
def _cleanup_registration() -> None:
    yield
    for key, owner in list(_PLUGIN_OWNERS.items()):
        unregister_channel_kind(key, plugin_id=owner)


def test_register_and_resolve() -> None:
    register_channel_kind("acme", _StubChannel, plugin_id="test")
    assert "acme" in BUILTIN_CHANNELS
    assert BUILTIN_CHANNELS["acme"] is _StubChannel


def test_register_replaces_same_owner() -> None:
    register_channel_kind("acme", _StubChannel, plugin_id="test")

    class _Other(BaseChannel):
        channel_type = "acme-other"

    # The same owner can replace its implementation on reload.
    register_channel_kind("acme", _Other, plugin_id="test")
    assert BUILTIN_CHANNELS["acme"] is _Other


def test_register_rejects_builtin_override() -> None:
    with pytest.raises(ValueError, match="builtin"):
        register_channel_kind("telegram", _StubChannel, plugin_id="test")


def test_register_rejects_empty_kind() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        register_channel_kind("  ", _StubChannel, plugin_id="test")


def test_register_rejects_non_class() -> None:
    with pytest.raises(TypeError, match="must be a class"):
        register_channel_kind("acme", lambda: None, plugin_id="test")  # type: ignore[arg-type]


def test_owner_conflict_and_unregister() -> None:
    register_channel_kind("acme", _StubChannel, plugin_id="first")
    try:
        assert "acme" in registered_channel_kinds()
        with pytest.raises(ValueError, match="owned"):
            register_channel_kind("acme", _StubChannel, plugin_id="second")
        with pytest.raises(ValueError, match="owned"):
            unregister_channel_kind("acme", plugin_id="second")
    finally:
        assert unregister_channel_kind("acme", plugin_id="first")
    assert "acme" not in registered_channel_kinds()


@pytest.mark.parametrize("owner", ["", "   "])
def test_empty_owner_rejected(owner: str) -> None:
    with pytest.raises(ValueError, match="plugin_id"):
        register_channel_kind("acme", _StubChannel, plugin_id=owner)
    with pytest.raises(ValueError, match="plugin_id"):
        unregister_channel_kind("acme", plugin_id=owner)


def test_owner_argument_required() -> None:
    with pytest.raises(TypeError):
        register_channel_kind("acme", _StubChannel)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        unregister_channel_kind("acme")  # type: ignore[call-arg]
