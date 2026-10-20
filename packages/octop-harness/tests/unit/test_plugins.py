"""Unit tests for octop_harness.plugins."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop_harness.plugins.context import PluginContext
from octop_harness.plugins.loader import load_plugin_dir
from octop_harness.plugins.manifest import PluginManifest
from octop_harness.plugins.registry import PluginRegistry
from octop_harness.plugins.tools import _tool_enabled

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "plugins" / "echo-tool"
_CHANNEL_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "plugins" / "acme-channel"


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    PluginRegistry.reset()
    yield
    PluginRegistry.reset()


def test_manifest_from_yaml(tmp_path: Path) -> None:
    (tmp_path / "plugin.yaml").write_text(
        "id: demo\nversion: 0.1.0\nname: Demo\nkind: tool\nentry: main.py\n",
        encoding="utf-8",
    )
    manifest = PluginManifest.load(tmp_path / "plugin.yaml")
    assert manifest.id == "demo"
    assert manifest.kind == "tool"


def test_context_rejects_wrong_kind(tmp_path: Path) -> None:
    manifest = PluginManifest(
        id="x",
        version="1",
        name="x",
        kind="hook",
        entry="main.py",
    )
    ctx = PluginContext(manifest=manifest, source_path=tmp_path)
    with pytest.raises(ValueError, match="not tool"):
        ctx.tool("t", lambda: None)


def test_load_echo_fixture() -> None:
    loaded = load_plugin_dir(_FIXTURE, install_deps=False)
    assert loaded.manifest.id == "echo-tool"
    assert loaded.tools[0].name == "echo_message"


def test_manifest_accepts_channel_kind(tmp_path: Path) -> None:
    (tmp_path / "plugin.yaml").write_text(
        "id: chan\nversion: 0.1.0\nname: Chan\nkind: channel\nentry: main.py\n",
        encoding="utf-8",
    )
    manifest = PluginManifest.load(tmp_path / "plugin.yaml")
    assert manifest.kind == "channel"


def test_manifest_rejects_unknown_kind(tmp_path: Path) -> None:
    (tmp_path / "plugin.yaml").write_text(
        "id: bad\nversion: 0.1.0\nname: Bad\nkind: teleport\nentry: main.py\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported plugin kind"):
        PluginManifest.load(tmp_path / "plugin.yaml")


def test_context_channel_registration(tmp_path: Path) -> None:
    class DummyChannel:
        pass

    manifest = PluginManifest(id="c", version="1", name="c", kind="channel", entry="main.py")
    ctx = PluginContext(manifest=manifest, source_path=tmp_path)
    ctx.channel(
        "acme",
        DummyChannel,
        label="Acme IM",
        intro_url="https://example.com",
        fields=[{"name": "token", "label": "Token", "type": "password", "required": True}],
    )
    loaded = ctx.to_loaded()
    assert len(loaded.channels) == 1
    reg = loaded.channels[0]
    assert reg.kind == "acme"
    assert reg.channel_cls is DummyChannel
    assert reg.label == "Acme IM"
    assert reg.fields[0]["name"] == "token"

    ctx.channel("Beta", DummyChannel, icon="  icon.png  ", intro_url="  https://example.com/b  ")
    omitted = ctx.to_loaded().channels[1]
    assert omitted.kind == "beta"
    assert omitted.label == "Beta"
    assert omitted.icon == "icon.png"
    assert omitted.intro_url == "https://example.com/b"


def test_context_channel_rejects_wrong_kind(tmp_path: Path) -> None:
    manifest = PluginManifest(id="x", version="1", name="x", kind="tool", entry="main.py")
    ctx = PluginContext(manifest=manifest, source_path=tmp_path)
    with pytest.raises(ValueError, match="not channel"):
        ctx.channel("acme", object)


def test_context_channel_validates_input(tmp_path: Path) -> None:
    manifest = PluginManifest(id="c", version="1", name="c", kind="channel", entry="main.py")
    ctx = PluginContext(manifest=manifest, source_path=tmp_path)
    with pytest.raises(ValueError, match="kind must not be empty"):
        ctx.channel("  ", object)
    with pytest.raises(ValueError, match="channel_cls must be"):
        ctx.channel("acme", "not-a-callable")  # type: ignore[arg-type]


def test_registry_rejects_channel_owner_conflict() -> None:
    from octop_harness.plugins.registry import ChannelRegistration, LoadedPlugin

    class A:
        pass

    class B:
        pass

    loaded1 = LoadedPlugin(
        manifest=PluginManifest(id="p1", version="1", name="p1", kind="channel", entry="m.py"),
        source_path=Path("."),
        channels=[ChannelRegistration(plugin_id="p1", kind="acme", channel_cls=A)],
    )
    loaded2 = LoadedPlugin(
        manifest=PluginManifest(id="p2", version="1", name="p2", kind="channel", entry="m.py"),
        source_path=Path("."),
        channels=[ChannelRegistration(plugin_id="p2", kind="acme", channel_cls=B)],
    )
    registry = PluginRegistry()
    registry.register(loaded1)
    with pytest.raises(ValueError, match="already owned"):
        registry.register(loaded2)
    regs = registry.all_channels()
    assert len(regs) == 1
    assert regs[0].channel_cls is A


def test_load_channel_fixture() -> None:
    loaded = load_plugin_dir(_CHANNEL_FIXTURE, install_deps=False)
    assert loaded.manifest.id == "acme-channel"
    assert loaded.manifest.kind == "channel"
    assert loaded.channels[0].kind == "acme"
    assert loaded.channels[0].label == "Acme IM"


def test_tool_enabled_defaults_on_when_plugin_globally_on() -> None:
    assert _tool_enabled("echo", "echo_message", agent_plugins={}, global_plugins={}) is True
    assert (
        _tool_enabled(
            "echo",
            "echo_message",
            agent_plugins={"echo": {"tools": {"echo_message": {"config": {"x": 1}}}}},
            global_plugins={"echo": True},
        )
        is True
    )
    assert (
        _tool_enabled(
            "echo",
            "echo_message",
            agent_plugins={"echo": {"tools": {"echo_message": {"enabled": False}}}},
            global_plugins={"echo": True},
        )
        is False
    )
    assert (
        _tool_enabled(
            "echo",
            "echo_message",
            agent_plugins={},
            global_plugins={"echo": False},
        )
        is False
    )


def test_channel_registry_update_and_unload(tmp_path: Path) -> None:
    from octop_harness.plugins.registry import ChannelRegistration, LoadedPlugin

    manifest = PluginManifest(id="owner", version="1", name="Owner", kind="channel", entry="main.py")
    registry = PluginRegistry()
    first = LoadedPlugin(
        manifest=manifest,
        source_path=tmp_path,
        channels=[ChannelRegistration(plugin_id="owner", kind="acme", channel_cls=object)],
    )
    registry.register(first)
    updated = LoadedPlugin(
        manifest=manifest,
        source_path=tmp_path,
        channels=[ChannelRegistration(plugin_id="owner", kind="new-kind", channel_cls=object)],
    )
    registry.register(updated)
    assert [reg.kind for reg in registry.all_channels()] == ["new-kind"]
    registry.unregister("owner")
    assert registry.all_channels() == []
