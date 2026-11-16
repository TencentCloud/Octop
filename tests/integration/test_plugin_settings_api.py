"""Generic plugin settings use host permissions and plugin-owned validation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_arbitrary_plugin_settings_dispatch_and_permissions(env_admin_alice):
    client, _server, admin, alice = env_admin_alice
    provider = SimpleNamespace(
        get_settings=AsyncMock(return_value={"arbitraryField": "old"}), save_settings=AsyncMock()
    )
    with (
        patch("octop.api.routers.plugin_settings._provider", return_value=provider),
        patch(
            "octop.api.routers.plugin_settings._context", AsyncMock(return_value={"channels": []})
        ),
    ):
        path = "/api/plugins/unrelated-plugin/settings"
        assert (await client.get(path, headers=alice)).status_code == 403
        assert (
            await client.put(path, headers=alice, json={"arbitraryField": "new"})
        ).status_code == 403
        assert (await client.get(path, headers=admin)).json() == {"arbitraryField": "old"}
        assert (
            await client.put(path, headers=admin, json={"arbitraryField": "new"})
        ).status_code == 200
        provider.save_settings.assert_awaited_once_with({"channels": []}, {"arbitraryField": "new"})
        provider.save_settings.side_effect = ValueError("invalid field")
        assert (
            await client.put(path, headers=admin, json={"arbitraryField": None})
        ).status_code == 400
