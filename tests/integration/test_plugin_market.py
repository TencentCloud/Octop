from __future__ import annotations

from typing import Any

import pytest

from octop.infra.market import clear_market_cache


@pytest.fixture(autouse=True)
def _empty_portal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_PORTAL_ORIGIN", "")
    clear_market_cache()


async def test_list_market_unavailable_without_portal(env: Any) -> None:
    client, _srv, auth = env
    response = await client.get("/api/plugins/market", headers=auth)
    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "PLUGIN_MARKET_FAILED"


async def test_market_requires_plugin_market_permission(env_admin_alice: Any) -> None:
    client, _srv, _admin_auth, alice_auth = env_admin_alice
    listed = await client.get("/api/plugins/market", headers=alice_auth)
    assert listed.status_code == 403, listed.text
    installed = await client.post(
        "/api/plugins/market/any-plugin/install",
        headers=alice_auth,
    )
    assert installed.status_code == 403, installed.text
