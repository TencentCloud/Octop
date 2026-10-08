"""Tests for plugin-contributed channel bridging (infra + API validation).

The full path (plugin.yaml ``kind: channel`` -> loader -> registry -> gateway
registration) needs the *updated* octop-harness; on test environments with a
released harness those tests skip. The bridging logic itself is exercised
with stub registrations so it is covered everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_HARNESS_FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "octop-harness"
    / "tests"
    / "fixtures"
    / "plugins"
)
_ACME = _HARNESS_FIXTURES / "acme-channel"


def _harness_supports_channel_kind() -> bool:
    try:
        from octop_harness.plugins.manifest import PLUGIN_KINDS

        return "channel" in PLUGIN_KINDS
    except ImportError:
        return False


@dataclass
class _StubReg:
    plugin_id: str
    kind: str
    channel_cls: Any
    label: str = ""
    icon: str = ""
    intro_url: str = ""
    fields: list[dict[str, Any]] = field(default_factory=list)


class _StubRegistry:
    def __init__(self, *regs: _StubReg) -> None:
        self._regs = list(regs)

    def all_channels(self) -> list[_StubReg]:
        return list(self._regs)


class _RecordingGateway:
    """Minimal stand-in for octop_gateway.channels.register_channel_kind."""

    def __init__(self, *, fail_on: set[str] | None = None) -> None:
        self.registered: dict[str, Any] = {}
        self._fail_on = fail_on or set()

    def __call__(self, kind: str, channel_cls: Any) -> None:
        if kind in self._fail_on:
            raise ValueError(f"kind {kind!r} already registered")
        self.registered[kind] = channel_cls


class _FakeChannel:
    channel_type = "acme"


def test_apply_plugin_channels_registers_kind() -> None:
    from octop.infra.gateway.plugin_channels import apply_plugin_channels

    gateway = _RecordingGateway()
    applied = apply_plugin_channels(
        registry=_StubRegistry(
            _StubReg(
                plugin_id="acme",
                kind="acme",
                channel_cls=_FakeChannel,
                label="Acme IM",
                fields=[{"name": "token", "label": "Token"}],
            )
        ),
        register=gateway,
    )
    assert [info.kind for info in applied] == ["acme"]
    assert gateway.registered["acme"] is _FakeChannel
    assert applied[0].to_dict()["label"] == "Acme IM"
    assert applied[0].to_dict()["fields"] == [{"name": "token", "label": "Token"}]


def test_apply_is_idempotent_and_first_wins() -> None:
    from octop.infra.gateway.plugin_channels import apply_plugin_channels

    class Second:
        pass

    gateway = _RecordingGateway()
    registry = _StubRegistry(
        _StubReg("a", "acme", _FakeChannel), _StubReg("b", "acme", Second)
    )
    first = apply_plugin_channels(registry=registry, register=gateway)
    second = apply_plugin_channels(registry=registry, register=gateway)
    # Replay is a no-op: the bridging layer dedupes before reaching the gateway.
    assert [info.kind for info in second] == ["acme"]
    assert gateway.registered == {"acme": _FakeChannel}
    assert first[0].plugin_id == "a"


def test_apply_never_shadows_builtin() -> None:
    from octop.infra.gateway.plugin_channels import apply_plugin_channels

    gateway = _RecordingGateway(fail_on={"telegram"})
    applied = apply_plugin_channels(
        registry=_StubRegistry(_StubReg("evil", "telegram", _FakeChannel)),
        register=gateway,
    )
    # The registration failure is contained to that one plugin...
    assert applied == []
    # ...and the builtin kind was never touched.
    assert "telegram" not in gateway.registered


def test_apply_skips_failing_plugin_but_keeps_others() -> None:
    from octop.infra.gateway.plugin_channels import apply_plugin_channels

    class Broken:
        pass

    gateway = _RecordingGateway(fail_on={"broken"})
    applied = apply_plugin_channels(
        registry=_StubRegistry(
            _StubReg("bad", "broken", Broken),
            _StubReg("good", "zeta", _FakeChannel, label="Zeta"),
        ),
        register=gateway,
    )
    assert [info.kind for info in applied] == ["zeta"]
    assert "broken" not in gateway.registered
    assert gateway.registered["zeta"] is _FakeChannel


def test_plugin_channel_kinds_summary() -> None:
    from octop.infra.gateway.plugin_channels import plugin_channel_kinds

    kinds = plugin_channel_kinds(
        registry=_StubRegistry(
            _StubReg("p1", "zeta", _FakeChannel, label="Zeta"),
            _StubReg("p2", "zeta", _FakeChannel),  # duplicate kind: first wins
            _StubReg("p3", "alpha", _FakeChannel),
        )
    )
    assert [k.kind for k in kinds] == ["alpha", "zeta"]  # sorted, deduped
    assert kinds[1].label == "Zeta"
    assert kinds[1].plugin_id == "p1"


def test_api_kind_validator_accepts_plugin_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import channels as channels_router

    # Patch the harness PluginRegistry used inside the validator so the test
    # works against released harness builds (which lack ChannelRegistration).
    class _PatchedRegistry:
        def all_channels(self) -> list[_StubReg]:
            return [_StubReg("p1", "acme", _FakeChannel)]

    monkeypatch.setattr(
        "octop_harness.plugins.registry.PluginRegistry", _PatchedRegistry
    )
    assert channels_router._validate_channel_kind("Telegram") == "telegram"
    assert channels_router._validate_channel_kind("acme") == "acme"
    with pytest.raises(ValueError, match="unknown channel kind"):
        channels_router._validate_channel_kind("nope")


def test_api_kind_validator_tolerates_old_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import channels as channels_router

    class _OldRegistry:  # released harness: no all_channels()
        pass

    monkeypatch.setattr(
        "octop_harness.plugins.registry.PluginRegistry", _OldRegistry
    )
    # Builtin kinds still validate; unknown kinds are rejected.
    assert channels_router._validate_channel_kind("telegram") == "telegram"
    with pytest.raises(ValueError, match="unknown channel kind"):
        channels_router._validate_channel_kind("acme")


@pytest.mark.skipif(
    not _harness_supports_channel_kind(),
    reason="installed octop-harness predates the 'channel' plugin kind",
)
def test_end_to_end_with_real_fixture_plugin() -> None:
    from octop.infra.gateway.plugin_channels import apply_plugin_channels
    from octop_harness.plugins import registry as harness_registry
    from octop_harness.plugins.loader import load_plugin_dir

    harness_registry.PluginRegistry.reset()
    try:
        loaded = load_plugin_dir(_ACME, install_deps=False)
        assert loaded.manifest.kind == "channel"
        applied = apply_plugin_channels(registry=harness_registry.PluginRegistry())
        assert "acme" in [info.kind for info in applied]
        from octop_gateway.channels import BUILTIN_CHANNELS

        assert BUILTIN_CHANNELS["acme"].channel_type == "acme"
    finally:
        harness_registry.PluginRegistry.reset()
