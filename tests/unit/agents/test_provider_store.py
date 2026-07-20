"""Unit tests for :mod:`octop.infra.agents.providers.store`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.agents.providers import KIND_TO_PROTOCOL, ProviderStore
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import DBPool
from octop.infra.db.repos.agents import AgentRow
from octop.infra.db.services import build_shared_services
from octop.infra.utils.paths import PathLayout


@pytest.fixture
def store(tmp_path: Path) -> ProviderStore:
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = DBPool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    return ProviderStore(
        provider_repo=services.repos.provider_repo,
    )


def _row(
    *,
    agent_id: str = "01AGENT",
    default_model: str | None = None,
) -> AgentRow:
    return AgentRow(
        id=1,
        agent_id=agent_id,
        user_id=1,
        name="bot",
        description=None,
        persona_mbti=None,
        default_model=default_model,
        system_prompt=None,
        enabled=1,
        config_json=None,
        last_state=None,
        last_error=None,
        created_at=0,
        updated_at=0,
    )


def test_kind_to_protocol_maps_openai_compatible_kinds() -> None:
    assert KIND_TO_PROTOCOL["openai"] == "openai"
    assert KIND_TO_PROTOCOL["ollama"] == "openai"
    assert KIND_TO_PROTOCOL["anthropic"] == "anthropic"


def test_build_harness_configs_skips_disabled(store: ProviderStore) -> None:
    pid = store._provider_repo.create(
        name="disabled",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
    )
    store._provider_repo.update(pid, enabled=False)
    store._provider_repo.create(
        name="enabled",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models_json=json.dumps([{"id": "m1", "name": "m1"}]),
    )

    providers = store.build_harness_configs()
    assert [p.id for p in providers] == ["enabled"]


def test_build_harness_configs_skips_missing_credentials(store: ProviderStore) -> None:
    store._provider_repo.create(name="no-url", kind="openai", api_key="sk-test")
    store._provider_repo.create(
        name="no-key",
        kind="openai",
        base_url="https://api.example.com/v1",
    )

    assert store.build_harness_configs() == []
    assert store.has_usable_providers() is False


def test_has_usable_providers_requires_enabled_model(store: ProviderStore) -> None:
    store._provider_repo.create(
        name="empty-models",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models_json=json.dumps([]),
    )
    assert store.has_usable_providers() is False

    store._provider_repo.create(
        name="ready",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models_json=json.dumps([{"id": "m1", "name": "m1", "enabled": True}]),
    )
    assert store.has_usable_providers() is True


def test_build_harness_configs_maps_kind_to_protocol(store: ProviderStore) -> None:
    store._provider_repo.create(
        name="anthropic",
        kind="anthropic",
        base_url="https://api.anthropic.com",
        api_key="sk-ant",
        models_json=json.dumps([{"id": "claude", "name": "claude"}]),
    )
    providers = store.build_harness_configs()
    assert providers[0].protocol == "anthropic"


def test_resolve_default_model_returns_none_when_stale(store: ProviderStore) -> None:
    store._provider_repo.create(
        name="hai",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models_json=json.dumps([{"id": "MiniMax-M2.7", "name": "MiniMax", "enabled": True}]),
    )
    ref = store.resolve_explicit_default_model(_row(default_model="openai/gpt-4o"), {})
    assert ref is None


def test_resolve_default_model_auto_returns_none(store: ProviderStore) -> None:
    store._provider_repo.create(
        name="hai",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models_json=json.dumps([{"id": "MiniMax-M2.7", "name": "MiniMax", "enabled": True}]),
    )
    ref = store.resolve_explicit_default_model(_row(default_model=None), {})
    assert ref is None


def test_resolve_default_model_returns_explicit_ref_when_usable(store: ProviderStore) -> None:
    store._provider_repo.create(
        name="hai",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models_json=json.dumps([{"id": "MiniMax-M2.7", "name": "MiniMax", "enabled": True}]),
    )
    ref = store.resolve_explicit_default_model(
        _row(default_model="hai/MiniMax-M2.7"),
        {},
    )
    assert ref == "hai/MiniMax-M2.7"


def test_manager_exposes_provider_store(tmp_path: Path) -> None:
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = DBPool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    manager = AgentManager(repos=services.repos, paths=services.paths)
    assert isinstance(manager.providers, ProviderStore)


def test_build_harness_configs_infers_vision_from_model_id(store: ProviderStore) -> None:
    store._provider_repo.create(
        name="p",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models_json=json.dumps(
            [
                {"id": "gpt-4o", "name": "GPT-4o", "enabled": True, "input": ["text"]},
                {"id": "deepseek-chat", "name": "DeepSeek", "enabled": True, "input": ["text"]},
            ]
        ),
    )
    models = store.build_harness_configs()[0].models
    gpt4o = next(m for m in models if m.id == "gpt-4o")
    deepseek = next(m for m in models if m.id == "deepseek-chat")
    assert "image" in gpt4o.input
    assert deepseek.input == ["text"]


@pytest.mark.parametrize(
    ("model_ref", "expected"),
    [
        ("p/text-only", "p/vision"),
        ("p/vision", "p/vision"),
        (None, "p/vision"),
    ],
)
def test_resolve_model_for_multimodal_turn(
    store: ProviderStore, model_ref: str | None, expected: str
) -> None:
    store._provider_repo.create(
        name="p",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models_json=json.dumps(
            [
                {"id": "text-only", "name": "text", "enabled": True, "input": ["text"]},
                {"id": "vision", "name": "vision", "enabled": True, "input": ["text", "image"]},
            ]
        ),
    )
    resolved = store.resolve_model_for_multimodal_turn(model_ref, needs_multimodal=True)
    assert resolved == expected


def test_resolve_first_model_ref_returns_first_enabled_model(store: ProviderStore) -> None:
    store._provider_repo.create(
        name="p1",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models_json=json.dumps(
            [
                {"id": "disabled", "name": "disabled", "enabled": False},
                {"id": "ready", "name": "ready", "enabled": True},
            ]
        ),
    )
    store._provider_repo.create(
        name="p2",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models_json=json.dumps([{"id": "other", "name": "other", "enabled": True}]),
    )

    assert store.resolve_first_model_ref() == "p1/ready"


def test_resolve_multimodal_model_ref_prefers_inferred_vision_model(store: ProviderStore) -> None:
    store._provider_repo.create(
        name="p",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models_json=json.dumps(
            [
                {"id": "text-only", "name": "text", "enabled": True, "input": ["text"]},
                {"id": "gpt-4o", "name": "GPT-4o", "enabled": True, "input": ["text"]},
            ]
        ),
    )
    assert store.resolve_multimodal_model_ref() == "p/gpt-4o"
