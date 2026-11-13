"""Tests for :mod:`octop.infra.agents.providers.harness_factory`."""

from __future__ import annotations

from unittest.mock import MagicMock

from octop_harness.config import ProviderConfig

from octop.infra.agents.providers.harness_factory import sync_providers_to_harness


def test_sync_bootstraps_when_factory_missing() -> None:
    harness_manager = MagicMock()
    provider = ProviderConfig(
        id="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        name="openai",
    )

    sync_providers_to_harness(harness_manager, [provider], shared_factory=None)

    harness_manager.add_provider.assert_called_once_with(provider)
    harness_manager.remove_provider.assert_not_called()


def test_sync_adds_and_removes_providers() -> None:
    harness_manager = MagicMock()
    shared_factory = MagicMock()
    shared_factory._providers = {"old": object()}
    keep = ProviderConfig(
        id="keep",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        name="keep",
    )

    sync_providers_to_harness(harness_manager, [keep], shared_factory=shared_factory)

    harness_manager.remove_provider.assert_called_once_with("old")
    harness_manager.add_provider.assert_called_once_with(keep)


def test_sync_forwards_magpie_session_header_unchanged() -> None:
    harness_manager = MagicMock()
    magpie = ProviderConfig(
        id="Magpie",
        base_url="http://127.0.0.1:3425/v1",
        api_key="magpie-octop",
        name="Magpie",
        headers={"User-Agent": "Octop/test"},
        session_header="X-Magpie-Session",
    )
    sync_providers_to_harness(harness_manager, [magpie], shared_factory=None)
    forwarded = harness_manager.add_provider.call_args.args[0]
    assert forwarded.session_header == "X-Magpie-Session"
    assert forwarded.headers == {"User-Agent": "Octop/test"}
    assert "X-Magpie-Session" not in forwarded.headers
