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
    Path(__file__).resolve().parents[3] / "octop-harness" / "tests" / "fixtures" / "plugins"
)
_ACME = _HARNESS_FIXTURES / "acme-channel"


def _harness_supports_channel_kind() -> bool:
    try:
        from octop_harness.plugins.manifest import PLUGIN_KINDS

        return "channel" in PLUGIN_KINDS
    except ImportError:
        return False


def _channel_fixture_ready() -> bool:
    """The acme fixture lives in a sibling octop-harness checkout, not the wheel."""
    return _harness_supports_channel_kind() and (_ACME / "plugin.yaml").is_file()


@pytest.fixture(autouse=True)
def reset_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.gateway import plugin_channels as bridge

    monkeypatch.setattr(bridge, "_APPLIED", {})
    monkeypatch.setattr(bridge, "_CLASSES", {})
    monkeypatch.setattr(bridge, "_ERRORS", {})
    monkeypatch.setattr(bridge, "_KIND_ERRORS", {})
    monkeypatch.setattr(bridge, "_CURRENT_ERRORS", {})


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

    def __call__(self, kind: str, channel_cls: Any, *, plugin_id: str = "") -> None:
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
        unregister=lambda *args, **kwargs: None,
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
    registry = _StubRegistry(_StubReg("a", "acme", _FakeChannel), _StubReg("b", "acme", Second))
    first = apply_plugin_channels(
        registry=registry, register=gateway, unregister=lambda *args, **kwargs: None
    )
    second = apply_plugin_channels(
        registry=registry, register=gateway, unregister=lambda *args, **kwargs: None
    )
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
        unregister=lambda *args, **kwargs: None,
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
        unregister=lambda *args, **kwargs: None,
    )
    assert [info.kind for info in applied] == ["zeta"]
    assert "broken" not in gateway.registered
    assert gateway.registered["zeta"] is _FakeChannel


def test_plugin_channel_kinds_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.gateway import plugin_channels
    from octop.infra.gateway.plugin_channels import plugin_channel_kinds

    infos = plugin_channels._summarize(
        [_StubReg("p1", "zeta", _FakeChannel, label="Zeta"), _StubReg("p3", "alpha", _FakeChannel)]
    )
    monkeypatch.setattr(plugin_channels, "_APPLIED", {info.kind: info for info in infos})
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

    monkeypatch.setattr("octop_harness.plugins.registry.PluginRegistry", _PatchedRegistry)
    from octop.infra.gateway import plugin_channels

    info = plugin_channels._summarize(_PatchedRegistry().all_channels())[0]
    monkeypatch.setattr(plugin_channels, "_APPLIED", {"acme": info})
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

    monkeypatch.setattr("octop_harness.plugins.registry.PluginRegistry", _OldRegistry)
    # Builtin kinds still validate; unknown kinds are rejected.
    assert channels_router._validate_channel_kind("telegram") == "telegram"
    with pytest.raises(ValueError, match="unknown channel kind"):
        channels_router._validate_channel_kind("acme")


@pytest.mark.skipif(
    not _channel_fixture_ready(),
    reason="channel plugin fixture is only in a sibling octop-harness checkout",
)
def test_end_to_end_with_real_fixture_plugin() -> None:
    from octop_harness.plugins import registry as harness_registry
    from octop_harness.plugins.loader import load_plugin_dir

    from octop.infra.gateway.plugin_channels import apply_plugin_channels

    harness_registry.PluginRegistry.reset()
    try:
        from octop_gateway.channel import BaseChannel

        loaded = load_plugin_dir(_ACME, install_deps=False)

        class RealChannel(BaseChannel):
            channel_type = "acme"

        loaded.channels[0].channel_cls = RealChannel
        assert loaded.manifest.kind == "channel"
        applied = apply_plugin_channels(registry=harness_registry.PluginRegistry())
        assert "acme" in [info.kind for info in applied]
        from octop_gateway.channels import BUILTIN_CHANNELS

        assert BUILTIN_CHANNELS["acme"].channel_type == "acme"
    finally:
        from octop_gateway.channels import unregister_channel_kind

        unregister_channel_kind("acme", plugin_id="acme-channel")
        from octop.infra.gateway import plugin_channels

        plugin_channels._APPLIED.clear()
        harness_registry.PluginRegistry.reset()


def test_reconcile_removes_disabled_and_failed_kinds(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.gateway import plugin_channels as bridge

    monkeypatch.setattr(bridge, "_APPLIED", {})
    removed: list[tuple[str, str]] = []

    def unregister(kind: str, *, plugin_id: str) -> None:
        removed.append((kind, plugin_id))

    gateway = _RecordingGateway()
    registry = _StubRegistry(_StubReg("owner", "acme", _FakeChannel))
    bridge.apply_plugin_channels(registry=registry, register=gateway, unregister=unregister)
    assert [info.kind for info in bridge.plugin_channel_kinds(registry=registry)] == ["acme"]
    bridge.apply_plugin_channels(registry=_StubRegistry(), register=gateway, unregister=unregister)
    assert removed == [("acme", "owner")]
    assert bridge.plugin_channel_kinds(registry=registry) == []


def test_reconcile_updates_same_kind_implementation(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.gateway import plugin_channels as bridge

    monkeypatch.setattr(bridge, "_APPLIED", {})
    gateway = _RecordingGateway()

    class Updated:
        pass

    bridge.apply_plugin_channels(
        registry=_StubRegistry(_StubReg("owner", "acme", _FakeChannel)),
        register=gateway,
        unregister=lambda *args, **kwargs: None,
    )
    bridge.apply_plugin_channels(
        registry=_StubRegistry(_StubReg("owner", "acme", Updated)),
        register=gateway,
        unregister=lambda *args, **kwargs: None,
    )
    assert gateway.registered["acme"] is Updated


@pytest.mark.asyncio
async def test_reload_stops_plugin_instances_before_replacing_factories() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from octop.infra.gateway.gateway import Gateway

    rows = [
        SimpleNamespace(kind="acme", channel_id="plugin-row"),
        SimpleNamespace(kind="telegram", channel_id="builtin-row"),
    ]
    events: list[str] = []

    async def stop(channel_id: str) -> None:
        events.append("stop:" + channel_id)

    async def start(row: Any) -> None:
        events.append("start:" + row.channel_id)

    fake = SimpleNamespace(
        _repos=SimpleNamespace(channel_repo=SimpleNamespace(list_all=lambda **kwargs: rows)),
        _channel_manager=object(),
        _unregister=AsyncMock(side_effect=stop),
        _safe_register_channel=AsyncMock(side_effect=start),
    )
    await Gateway.reload_plugin_channels(fake, lambda: events.append("apply"), kinds={"acme"})
    assert events == ["stop:plugin-row", "apply", "start:plugin-row"]


def test_no_change_leaves_factories_registered() -> None:
    from unittest.mock import Mock

    from octop.infra.gateway import plugin_channels as bridge

    reg = _StubRegistry(_StubReg("owner", "acme", _FakeChannel))
    register, unregister = Mock(), Mock()
    bridge.apply_plugin_channels(registry=reg, register=register, unregister=unregister)
    assert bridge.changed_plugin_channel_kinds(reg) == set()
    bridge.apply_plugin_channels(registry=reg, register=register, unregister=unregister)
    assert register.call_count == 1
    unregister.assert_not_called()


def test_registration_failure_exposed_as_status() -> None:
    from octop.infra.gateway import plugin_channels as bridge

    bridge.apply_plugin_channels(
        registry=_StubRegistry(_StubReg("broken", "acme", _FakeChannel)),
        register=_RecordingGateway(fail_on={"acme"}),
        unregister=lambda *args, **kwargs: None,
    )
    assert "broken" in bridge.registration_errors()
    assert bridge.plugin_channel_kinds(registry=_StubRegistry()) == []


@pytest.mark.asyncio
async def test_registration_failure_reaches_mutation_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from octop.infra.errors import OctopError
    from octop.infra.gateway import plugin_channels as bridge
    from octop.infra.server import OctopServer

    monkeypatch.setattr(bridge, "_CURRENT_ERRORS", {"broken": "not BaseChannel"})
    fake = SimpleNamespace(app_runtime=None, _apply_plugin_channels=lambda: None)
    with pytest.raises(OctopError):
        await OctopServer.refresh_plugin_channels(fake)


@pytest.mark.asyncio
async def test_unrelated_plugin_change_does_not_restart_channels() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from octop.infra.gateway.gateway import Gateway

    fake = SimpleNamespace(
        _repos=SimpleNamespace(
            channel_repo=SimpleNamespace(
                list_all=lambda **kwargs: [SimpleNamespace(kind="acme", channel_id="a")]
            )
        ),
        _channel_manager=object(),
        _unregister=AsyncMock(),
        _safe_register_channel=AsyncMock(),
    )
    apply = Mock()
    await Gateway.reload_plugin_channels(fake, apply, kinds=set())
    fake._unregister.assert_not_awaited()
    fake._safe_register_channel.assert_not_awaited()
    apply.assert_called_once()


def test_old_gateway_capability_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop_gateway import channels

    from octop.infra.gateway import plugin_channels as bridge

    monkeypatch.delattr(channels, "register_channel_kind", raising=False)
    monkeypatch.delattr(channels, "unregister_channel_kind", raising=False)
    result = bridge.apply_plugin_channels(
        registry=_StubRegistry(_StubReg("owner", "acme", _FakeChannel))
    )
    assert result == []
    assert "upgrade gateway" in bridge.registration_errors()["owner"]


def test_failed_class_is_observed_without_repeated_registration() -> None:
    from unittest.mock import Mock

    from octop.infra.gateway import plugin_channels as bridge

    registry = _StubRegistry(_StubReg("bad", "broken", _FakeChannel))
    register = Mock(side_effect=ValueError("invalid class"))
    bridge.apply_plugin_channels(registry=registry, register=register, unregister=Mock())
    assert bridge.changed_plugin_channel_kinds(registry) == set()
    bridge.apply_plugin_channels(registry=registry, register=register, unregister=Mock())
    assert register.call_count == 1
    assert "bad" in bridge.registration_errors()
    assert bridge.current_registration_errors() == {}


def test_unregister_failure_does_not_skip_sibling_kind() -> None:
    from unittest.mock import Mock

    from octop.infra.gateway import plugin_channels as bridge

    first = _StubRegistry(
        _StubReg("owner", "alpha", _FakeChannel), _StubReg("owner", "beta", _FakeChannel)
    )
    bridge.apply_plugin_channels(registry=first, register=Mock(), unregister=Mock())

    class Updated:
        pass

    updated = _StubRegistry(_StubReg("owner", "alpha", Updated), _StubReg("owner", "beta", Updated))

    def unregister(kind: str, **kwargs: Any) -> None:
        if kind == "alpha":
            raise ValueError("cannot remove alpha")

    register = Mock()
    bridge.apply_plugin_channels(registry=updated, register=register, unregister=unregister)
    register.assert_called_once_with("beta", Updated, plugin_id="owner")


@pytest.mark.asyncio
async def test_existing_failed_registration_does_not_fail_unrelated_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock

    from octop.infra.gateway import plugin_channels as bridge
    from octop.infra.server import OctopServer

    registry = _StubRegistry(_StubReg("bad", "broken", _FakeChannel))
    register = Mock(side_effect=ValueError("invalid class"))

    def apply() -> None:
        bridge.apply_plugin_channels(registry=registry, register=register, unregister=Mock())

    apply()
    monkeypatch.setattr("octop.infra.server.PluginRegistry", lambda: registry)
    await OctopServer.refresh_plugin_channels(
        SimpleNamespace(app_runtime=None, _apply_plugin_channels=apply)
    )
    assert register.call_count == 1
    assert "bad" in bridge.registration_errors()


@pytest.mark.asyncio
async def test_removed_kind_retries_unregister_without_blocking_unrelated_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from octop.infra.errors import OctopError
    from octop.infra.gateway import plugin_channels as bridge
    from octop.infra.server import OctopServer

    gateway = _RecordingGateway()
    registry = _StubRegistry(_StubReg("owner", "acme", _FakeChannel))
    attempts: list[tuple[str, str]] = []
    failing = True

    def unregister(kind: str, *, plugin_id: str) -> None:
        attempts.append((kind, plugin_id))
        if failing:
            raise ValueError("cannot remove acme")
        del gateway.registered[kind]

    def apply() -> None:
        bridge.apply_plugin_channels(registry=registry, register=gateway, unregister=unregister)

    monkeypatch.setattr("octop.infra.server.PluginRegistry", lambda: registry)
    server = SimpleNamespace(app_runtime=None, _apply_plugin_channels=apply)
    apply()
    registry._regs.clear()
    with pytest.raises(OctopError):
        await OctopServer.refresh_plugin_channels(server)
    assert gateway.registered == {"acme": _FakeChannel}
    assert "acme" in bridge._APPLIED
    assert "acme" not in bridge._CLASSES
    assert "owner" in bridge.current_registration_errors()
    assert bridge.plugin_channel_kinds(registry=registry) == []
    assert bridge.changed_plugin_channel_kinds(registry) == {"acme"}

    # Existing cleanup failure remains visible, but a sibling can still register.
    registry._regs.append(_StubReg("owner", "beta", _FakeChannel))
    await OctopServer.refresh_plugin_channels(server)
    assert attempts == [("acme", "owner")] * 2
    assert gateway.registered == {"acme": _FakeChannel, "beta": _FakeChannel}
    assert "owner" in bridge.registration_errors()
    assert bridge.current_registration_errors() == {}
    assert [info.kind for info in bridge.plugin_channel_kinds(registry=registry)] == ["beta"]

    failing = False
    await OctopServer.refresh_plugin_channels(server)
    assert attempts == [("acme", "owner")] * 3
    assert gateway.registered == {"beta": _FakeChannel}
    assert set(bridge._APPLIED) == set(bridge._CLASSES) == {"beta"}
    assert bridge._KIND_ERRORS == {}
    assert bridge.registration_errors() == bridge.current_registration_errors() == {}
    assert bridge.changed_plugin_channel_kinds(registry) == set()
    registry._regs.clear()
    await OctopServer.refresh_plugin_channels(server)
    assert gateway.registered == bridge._APPLIED == bridge._CLASSES == bridge._KIND_ERRORS == {}
    assert bridge.plugin_channel_kinds(registry=registry) == []


def test_removing_failed_registration_clears_kind_errors() -> None:
    from octop.infra.gateway import plugin_channels as bridge

    gateway = _RecordingGateway(fail_on={"acme"})
    registry = _StubRegistry(_StubReg("owner", "acme", _FakeChannel))

    def unregister(kind: str, *, plugin_id: str) -> None:
        pytest.fail("a failed registration must not unregister a gateway kind")

    bridge.apply_plugin_channels(registry=registry, register=gateway, unregister=unregister)
    assert "owner" in bridge.registration_errors()
    registry._regs.clear()
    bridge.apply_plugin_channels(registry=registry, register=gateway, unregister=unregister)
    assert gateway.registered == bridge._APPLIED == bridge._CLASSES == bridge._KIND_ERRORS == {}
    assert bridge.registration_errors() == bridge.current_registration_errors() == {}
    assert bridge.plugin_channel_kinds(registry=registry) == []
