"""A catalog upgrade reaches existing dashboards and runtime without reconfiguration."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from octop.infra.agents.providers import store
from octop.infra.agents.providers.presets import load_provider_presets
from octop.infra.agents.providers.store import ProviderStore
from tests.support.app import octop_client
from tests.support.auth import auth_header, bootstrap_admin, create_user


async def test_restart_adds_enabled_models_and_preserves_user_choices(
    tmp_octop_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store, "_PRESET_PROVIDER_KEYS", None)
    bundled = load_provider_presets()
    name = "Example API"
    base_url = "https://api.example.com/v1"
    old_models: list[dict[str, Any]] = [
        {"id": "old-enabled", "name": "My default", "enabled": True, "context_window": 1234},
        {"id": "old-disabled", "enabled": False},
        {"id": "user-added", "enabled": True},
    ]
    old_preset = {
        "id": "example-preset",
        "name": name,
        "protocol": "openai",
        "base_url": base_url,
        "models": old_models[:2],
    }
    with patch(
        "octop.infra.agents.providers.presets.load_provider_presets",
        return_value=[*bundled, old_preset],
    ):
        async with octop_client(tmp_octop_home) as (client, srv):
            await bootstrap_admin(client, tmp_octop_home)
            auth = await auth_header(client)
            await create_user(client, auth, username="model-sync-user")
            response = await client.post(
                "/api/admin/providers",
                headers=auth,
                json={
                    "name": name,
                    "kind": "openai",
                    "base_url": base_url,
                    "api_key": "keep-key",
                    "models": old_models,
                },
            )
            response.raise_for_status()
            provider_id = response.json()["id"]
            srv.services.settings_repo.set_active_model(name, "old-enabled")
            agent_id = srv.services.agent_repo.list_all()[0].agent_id
            default_model = f"{name}/old-enabled"
            srv.services.agent_repo.update_config(agent_id, default_model=default_model)

    new_model = {
        "id": "new-model",
        "name": "New model",
        "enabled": False,
        "context_window": 100000,
        "max_input_tokens": 96000,
        "max_output_tokens": 4000,
    }
    upgraded = {
        **old_preset,
        "models": [
            {"id": "old-enabled", "context_window": 99999},
            {"id": "old-disabled", "enabled": True},
            new_model,
        ],
    }
    with patch(
        "octop.infra.agents.providers.presets.load_provider_presets",
        return_value=[*bundled, upgraded],
    ):
        async with octop_client(tmp_octop_home) as (client, srv):
            auth = await auth_header(client)
            user_auth = await auth_header(client, username="model-sync-user")
            rows = (await client.get("/api/admin/providers", headers=auth)).json()
            row = next(r for r in rows if r["id"] == provider_id)
            assert [m["id"] for m in row["models"]] == [
                "old-enabled",
                "old-disabled",
                "user-added",
                "new-model",
            ]
            stored = srv.services.provider_repo.get(provider_id).get_models()
            assert stored == [*old_models, {**new_model, "enabled": True}]
            assert srv.services.settings_repo.get_active_model() == (name, "old-enabled")
            assert srv.services.agent_repo.get(agent_id).default_model == default_model
            resolved = (await client.get("/api/providers/resolved", headers=user_auth)).json()
            assert {m["model"] for m in resolved if m["provider_name"] == name} == {
                "old-enabled",
                "user-added",
                "new-model",
            }
            configs = ProviderStore(
                provider_repo=srv.services.provider_repo
            ).build_harness_configs()
            provider = next(p for p in configs if p.name == name)
            assert {m.id for m in provider.models} == {"old-enabled", "user-added", "new-model"}

            stored[-1]["enabled"] = False
            response = await client.patch(
                f"/api/admin/providers/{provider_id}", headers=auth, json={"models": stored}
            )
            response.raise_for_status()

        async with octop_client(tmp_octop_home) as (client, srv):
            assert srv.services.provider_repo.get(provider_id).get_models() == stored
            assert srv.services.settings_repo.get_active_model() == (name, "old-enabled")
            assert srv.services.agent_repo.get(agent_id).default_model == default_model
            user_auth = await auth_header(client, username="model-sync-user")
            resolved = (await client.get("/api/providers/resolved", headers=user_auth)).json()
            assert "new-model" not in {m["model"] for m in resolved if m["provider_name"] == name}
