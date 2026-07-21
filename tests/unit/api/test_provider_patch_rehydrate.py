"""Unit tests: skip harness rehydrate when provider patch is note-only."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.api.routers.providers import (
    ProviderPatchBody,
    _patch_requires_provider_rehydrate,
    admin_patch_provider,
)


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

    server.services.provider_repo.update.assert_called_once()
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

    on_changed.assert_awaited_once_with(provider_name="test-openai")
