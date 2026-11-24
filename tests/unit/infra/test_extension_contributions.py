"""``octop.extensions`` contributions to Octop's built-in registries."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from octop.i18n import tr
from octop.i18n.domains.tools import hitl_tool_catalog
from octop.infra import extensions
from octop.infra.agents.providers.presets import load_provider_presets
from octop.infra.errors import OctopError
from octop.infra.extensions import clear_extension_caches
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.users.preferences import validate_sidebar_nav


class _Product:
    def i18n_bundles(self) -> dict[str, Any]:
        return {
            "en": {
                "my_product": {"hello": "Hello {name}"},
                "tools": {"my_lookup": "Look up", "my_send": "Send"},
                # Built-in strings are never replaced.
                "errors": {"NOT_FOUND": "overridden"},
            },
            "zh": {"my_product": {"hello": "你好 {name}"}},
        }

    def provider_presets(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "my-cloud",
                "name": "My Cloud",
                "base_url": "https://api.example.com/v1",
                "protocol": "openai",
                "models": [{"id": "m1", "name": "M1"}],
            },
            # An id Octop already ships is skipped.
            {"id": "ollama", "name": "Not Ollama"},
        ]

    def hitl_excluded_tools(self) -> list[str]:
        return ["my_lookup"]

    def sidebar_nav_keys(self) -> list[str]:
        return ["my-product"]

    def virtual_channels(self) -> list[str]:
        return ["my_room"]


@pytest.fixture()
def product(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    entries = [SimpleNamespace(name="product", load=lambda: _Product())]
    monkeypatch.setattr(extensions, "entry_points", lambda group: entries)
    clear_extension_caches()
    yield
    clear_extension_caches()


@pytest.fixture()
def no_extensions(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(extensions, "entry_points", lambda group: [])
    clear_extension_caches()
    yield
    clear_extension_caches()


def test_i18n_bundles_add_keys_without_replacing_built_ins(product: None) -> None:
    assert tr("my_product.hello", "zh", name="A") == "你好 A"
    assert tr("my_product.hello", "en", name="A") == "Hello A"
    assert tr("errors.NOT_FOUND", "en") != "overridden"


def test_hitl_excluded_tools_leave_the_approval_picker(product: None) -> None:
    names = {entry.name for entry in hitl_tool_catalog()}
    assert "my_send" in names
    assert "my_lookup" not in names


def test_provider_presets_come_first_and_never_replace_a_bundled_id(product: None) -> None:
    presets = load_provider_presets()
    assert presets[0]["id"] == "my-cloud"
    ollama = [p for p in presets if p["id"] == "ollama"]
    assert len(ollama) == 1 and ollama[0]["name"] != "Not Ollama"


def test_sidebar_nav_keys_are_accepted(product: None) -> None:
    _, items = validate_sidebar_nav({"groups": [], "items": [{"key": "my-product"}]})
    assert [item.key for item in items] == ["my-product"]


def test_unknown_sidebar_nav_key_is_still_rejected(no_extensions: None) -> None:
    with pytest.raises(OctopError):
        validate_sidebar_nav({"groups": [], "items": [{"key": "my-product"}]})


def test_virtual_channels(product: None) -> None:
    assert ThreadRegistry.is_virtual_channel("my_room")
    assert ThreadRegistry.is_virtual_channel("dashboard")
    assert not ThreadRegistry.is_virtual_channel("telegram")


def test_without_extensions_registries_are_unchanged(no_extensions: None) -> None:
    assert not ThreadRegistry.is_virtual_channel("my_room")
    assert all(p["id"] != "my-cloud" for p in load_provider_presets())
    with pytest.raises(KeyError):
        tr("my_product.hello", "en")


def test_contribution_values_must_be_names(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = SimpleNamespace(virtual_channels=lambda: [""])
    monkeypatch.setattr(
        extensions, "entry_points", lambda group: [SimpleNamespace(name="bad", load=lambda: bad)]
    )
    clear_extension_caches()
    try:
        with pytest.raises(ValueError, match="virtual_channels"):
            ThreadRegistry.is_virtual_channel("x")
    finally:
        clear_extension_caches()
