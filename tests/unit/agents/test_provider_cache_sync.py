from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from octop_harness import HarnessAgentManager
from octop_harness.config import ModelConfig, ProviderConfig

from octop.infra.agents.providers.harness_factory import sync_providers_to_harness


@pytest.fixture
def manager(tmp_path: Path) -> Iterator[HarnessAgentManager]:
    providers = [
        ProviderConfig(
            id=name,
            base_url=f"https://{name}.example.com/v1",
            api_key=f"sk-{name}",
            models=[ModelConfig(id="model")],
        )
        for name in ("first", "second")
    ]
    manager = HarnessAgentManager(providers=providers, log_dir=tmp_path / "logs")
    yield manager
    assert manager.shared_factory is not None
    manager.shared_factory.close()


def test_sync_preserves_models_when_provider_configs_are_unchanged(
    manager: HarnessAgentManager,
) -> None:
    factory = manager.shared_factory
    assert factory is not None
    first = factory.get_chat_model("first/model")
    second = factory.get_chat_model("second/model")
    providers = deepcopy(factory.provider_configs())

    sync_providers_to_harness(manager, providers, shared_factory=factory)

    assert factory.get_chat_model("first/model") is first
    assert factory.get_chat_model("second/model") is second


@pytest.mark.parametrize(
    "changes",
    [
        {"api_key": "sk-rotated"},
        {"base_url": "https://replacement.example.com/v1"},
        {"headers": {"X-Tenant": "updated"}},
        {"stream_usage": False},
        {"models": [ModelConfig(id="model", max_output_tokens=2048)]},
    ],
    ids=["api-key", "base-url", "headers", "stream-usage", "model-settings"],
)
def test_sync_refreshes_changed_provider_without_evicting_unrelated_models(
    manager: HarnessAgentManager, changes: dict[str, Any]
) -> None:
    factory = manager.shared_factory
    assert factory is not None
    first = factory.get_chat_model("first/model")
    second = factory.get_chat_model("second/model")
    providers = deepcopy(factory.provider_configs())
    providers[0] = replace(providers[0], **changes)

    sync_providers_to_harness(manager, providers, shared_factory=factory)

    refreshed = factory.get_chat_model("first/model")
    assert refreshed is not first
    assert factory.provider_configs()[0] == providers[0]
    assert factory.get_chat_model("second/model") is second
    if "api_key" in changes:
        assert refreshed.openai_api_key.get_secret_value() == "sk-rotated"


def test_sync_adds_provider_without_evicting_existing_models(manager: HarnessAgentManager) -> None:
    factory = manager.shared_factory
    assert factory is not None
    first = factory.get_chat_model("first/model")
    providers = deepcopy(factory.provider_configs())
    providers.append(
        ProviderConfig(
            id="third",
            base_url="https://third.example.com/v1",
            api_key="sk-third",
            models=[ModelConfig(id="model")],
        )
    )

    sync_providers_to_harness(manager, providers, shared_factory=factory)

    assert factory.get_chat_model("first/model") is first
    assert factory.get_chat_model("third/model").openai_api_key.get_secret_value() == "sk-third"


def test_sync_removes_only_deleted_provider_models(manager: HarnessAgentManager) -> None:
    factory = manager.shared_factory
    assert factory is not None
    factory.get_chat_model("first/model")
    second = factory.get_chat_model("second/model")
    providers = deepcopy(factory.provider_configs())[1:]

    sync_providers_to_harness(manager, providers, shared_factory=factory)

    with pytest.raises(ValueError, match="Unknown provider"):
        factory.get_chat_model("first/model")
    assert factory.get_chat_model("second/model") is second
