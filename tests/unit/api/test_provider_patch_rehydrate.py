"""Unit tests: skip harness rehydrate when provider patch is note-only."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octop.api.routers.providers import (
    ProviderPatchBody,
    _patch_requires_provider_rehydrate,
    _provider_patch_updates,
    _row_to_dict,
    admin_patch_provider,
)


def test_revoke_api_key_is_an_explicit_clear() -> None:
    body = ProviderPatchBody.model_validate({"api_key": None})
    assert _provider_patch_updates(body, current_extra_json=None) == {"api_key": None}


def test_blank_api_key_clears_without_touching_other_fields() -> None:
    body = ProviderPatchBody.model_validate({"api_key": "   "})
    assert _provider_patch_updates(body, current_extra_json=None) == {"api_key": None}


def test_note_only_patch_does_not_include_api_key() -> None:
    body = ProviderPatchBody.model_validate({"note": "ops memo"})
    assert _provider_patch_updates(body, current_extra_json='{"headers": {}}') == {
        "note": "ops memo"
    }


def test_stream_usage_patch_rewrites_extra_without_clearing_api_key() -> None:
    body = ProviderPatchBody.model_validate({"stream_usage": False})
    assert _provider_patch_updates(body, current_extra_json='{"headers": {"X-A": "1"}}') == {
        "extra_json": '{"headers": {"X-A": "1"}, "stream_usage": false}'
    }


def test_default_model_patch_is_stored_and_can_be_cleared() -> None:
    body = ProviderPatchBody.model_validate({"model": "deepseek-v3"})
    updates = _provider_patch_updates(body, current_extra_json='{"headers": {"X-A": "1"}}')
    extra = json.loads(updates["extra_json"])
    assert extra["default_model"] == "deepseek-v3"
    assert extra["headers"] == {"X-A": "1"}
    assert "api_key" not in updates
    assert _patch_requires_provider_rehydrate(body) is False

    cleared = ProviderPatchBody.model_validate({"model": None})
    cleared_extra = json.loads(
        _provider_patch_updates(cleared, current_extra_json=updates["extra_json"])["extra_json"]
    )
    assert "default_model" not in cleared_extra
    assert cleared_extra["headers"] == {"X-A": "1"}


def test_row_to_dict_uses_saved_default_model_not_the_first_model() -> None:
    row = SimpleNamespace(
        id=1,
        name="custom",
        kind="openai",
        base_url="https://example.invalid",
        api_key="sk",
        note=None,
        enabled=1,
        extra_json=None,
        get_models=lambda: [{"id": "first", "name": "First"}],
    )
    assert _row_to_dict(row)["model"] is None

    row.extra_json = '{"default_model": "deepseek-v3"}'
    assert _row_to_dict(row)["model"] == "deepseek-v3"


def test_patch_note_only_does_not_require_rehydrate() -> None:
    body = ProviderPatchBody.model_validate({"note": "ops memo"})
    assert _patch_requires_provider_rehydrate(body) is False


def test_patch_models_requires_rehydrate() -> None:
    body = ProviderPatchBody.model_validate(
        {"models": [{"id": "m1", "name": "m1", "enabled": True}]}
    )
    assert _patch_requires_provider_rehydrate(body) is True


def test_patch_note_and_api_key_requires_rehydrate() -> None:
    body = ProviderPatchBody.model_validate({"note": "x", "api_key": "sk-new"})
    assert _patch_requires_provider_rehydrate(body) is True


@pytest.mark.asyncio
async def test_admin_patch_note_only_skips_on_provider_changed() -> None:
    on_changed = AsyncMock()
    row = MagicMock()
    row.id = 1
    row.name = "test-openai"
    server = MagicMock()
    server.services.provider_repo.get.side_effect = [row, row]
    server.services.provider_repo.update = MagicMock()
    server.app_runtime.agent_registry.on_provider_changed = on_changed

    body = ProviderPatchBody.model_validate({"note": "only note"})
    await admin_patch_provider(provider_id=1, body=body, _=None, server=server)

    server.services.provider_repo.update.assert_called_once_with(1, note="only note")
    on_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_patch_api_key_calls_on_provider_changed() -> None:
    on_changed = AsyncMock()
    row = MagicMock()
    row.id = 1
    row.name = "test-openai"
    server = MagicMock()
    server.services.provider_repo.get.side_effect = [row, row]
    server.services.provider_repo.update = MagicMock()
    server.app_runtime.agent_registry.on_provider_changed = on_changed

    body = ProviderPatchBody.model_validate({"api_key": "sk-new"})
    await admin_patch_provider(provider_id=1, body=body, _=None, server=server)

    server.services.provider_repo.update.assert_called_once_with(1, api_key="sk-new")
    on_changed.assert_awaited_once_with(provider_name="test-openai")


@pytest.mark.asyncio
async def test_admin_patch_null_api_key_clears_stored_key() -> None:
    on_changed = AsyncMock()
    row = MagicMock()
    row.id = 1
    row.name = "DeepSeek"
    server = MagicMock()
    server.services.provider_repo.get.side_effect = [row, row]
    server.services.provider_repo.update = MagicMock()
    server.app_runtime.agent_registry.on_provider_changed = on_changed

    body = ProviderPatchBody.model_validate({"api_key": None})
    await admin_patch_provider(provider_id=1, body=body, _=None, server=server)

    server.services.provider_repo.update.assert_called_once_with(1, api_key=None)
    on_changed.assert_awaited_once_with(provider_name="DeepSeek")


@pytest.mark.asyncio
async def test_admin_patch_models_clears_stale_agent_default_and_active() -> None:
    on_changed = AsyncMock()
    row = MagicMock()
    row.id = 1
    row.name = "hai"
    server = MagicMock()
    server.services.provider_repo.get.side_effect = [row, row]
    server.services.provider_repo.update = MagicMock()
    server.app_runtime.agent_registry.on_provider_changed = on_changed

    body = ProviderPatchBody.model_validate(
        {"models": [{"id": "keep", "name": "keep", "enabled": True}]}
    )
    with patch("octop.api.routers.providers.clear_stale_pins_for_provider") as clear_pins:
        await admin_patch_provider(provider_id=1, body=body, _=None, server=server)

    clear_pins.assert_called_once_with(
        agent_repo=server.services.agent_repo,
        settings_repo=server.services.settings_repo,
        provider_name="hai",
        models=body.models,
    )
    on_changed.assert_awaited_once_with(provider_name="hai")
