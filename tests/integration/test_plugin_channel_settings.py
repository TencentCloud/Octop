from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_channel_plugin_settings_visible_to_authenticated_channel_user(env_admin_alice):
    client, _server, _admin, alice = env_admin_alice
    settings = [{"plugin_id": "social", "name": "custom_switch"}]
    with patch(
        "octop.infra.gateway.plugin_channels.plugin_channel_settings", return_value=settings
    ):
        response = await client.get("/api/channels/plugin-settings", headers=alice)
    assert response.status_code == 200
    assert response.json() == settings
