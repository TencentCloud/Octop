"""Integration tests for the in-tree plugin marketplace."""

from __future__ import annotations

from typing import Any


async def test_list_market_catalog(env: Any) -> None:
    client, _srv, auth = env
    r = await client.get("/api/plugins/market", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert body
    sample = next(item for item in body if not item.get("error"))
    assert sample.get("id")
    assert "installed" in sample
    icon = sample.get("icon") or ""
    if icon.startswith("/api/"):
        assert "/market/" in icon


async def test_install_from_market(env: Any) -> None:
    client, srv, auth = env
    catalog = (await client.get("/api/plugins/market", headers=auth)).json()
    sample = next(item for item in catalog if not item.get("error") and not item.get("installed"))
    plugin_id = sample["id"]

    r = await client.post(
        f"/api/plugins/market/{plugin_id}/install",
        headers=auth,
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == plugin_id

    listing = (await client.get("/api/plugins", headers=auth)).json()
    assert any(p.get("id") == plugin_id for p in listing)

    market = (await client.get("/api/plugins/market", headers=auth)).json()
    row = next(item for item in market if item.get("id") == plugin_id)
    assert row["installed"] is True
    assert row.get("update_available") is False

    # Already installed without force → conflict
    again = await client.post(
        f"/api/plugins/market/{plugin_id}/install",
        headers=auth,
    )
    assert again.status_code == 409, again.text

    forced = await client.post(
        f"/api/plugins/market/{plugin_id}/install?force=true",
        headers=auth,
    )
    assert forced.status_code == 200, forced.text

    # Catalog icon asset is readable before/after install
    icon_path = (sample.get("icon") or "").replace("/api", "")
    if icon_path.startswith("/plugins/market/"):
        asset = await client.get(f"/api{icon_path}", headers=auth)
        assert asset.status_code == 200, asset.text

    # Non-image assets under the catalog must not be served
    blocked = await client.get(
        f"/api/plugins/market/{plugin_id}/ui/main.py",
        headers=auth,
    )
    assert blocked.status_code == 404, blocked.text

    assert srv.plugin_manager is not None
    assert srv.plugin_manager.plugin_dir(plugin_id) is not None


async def test_market_update_available_flag(env: Any) -> None:
    client, srv, auth = env
    assert srv.plugin_manager is not None
    catalog = (await client.get("/api/plugins/market", headers=auth)).json()
    sample = next(item for item in catalog if not item.get("error") and not item.get("installed"))
    plugin_id = sample["id"]

    inst = await client.post(
        f"/api/plugins/market/{plugin_id}/install",
        headers=auth,
    )
    assert inst.status_code == 200, inst.text

    # Downgrade local version so catalog reports an update.
    local_yaml = srv.plugin_manager.plugin_dir(plugin_id)
    assert local_yaml is not None
    yaml_path = local_yaml / "plugin.yaml"
    text = yaml_path.read_text(encoding="utf-8")
    yaml_path.write_text(
        text.replace(f"version: {sample['version']}", "version: 0.0.1", 1),
        encoding="utf-8",
    )

    market = (await client.get("/api/plugins/market", headers=auth)).json()
    row = next(item for item in market if item.get("id") == plugin_id)
    assert row["installed"] is True
    assert row["update_available"] is True
    assert row["installed_version"] == "0.0.1"


async def test_market_install_requires_admin(env_admin_alice: Any) -> None:
    client, _srv, _admin_auth, alice_auth = env_admin_alice
    catalog = (await client.get("/api/plugins/market", headers=alice_auth)).json()
    assert catalog
    plugin_id = next(item["id"] for item in catalog if not item.get("error"))
    r = await client.post(
        f"/api/plugins/market/{plugin_id}/install",
        headers=alice_auth,
    )
    assert r.status_code == 403, r.text
