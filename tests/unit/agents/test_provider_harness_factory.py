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
