"""Package-scoped API catalogs, writes and display order."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.parametrize("preset_id", ["tencent-hy-token-plan", "tencent-token-plan"])
async def test_package_fetch_uses_its_own_catalog_without_remote_discovery(
    env: Any, preset_id: str
) -> None:
    client, _srv, auth = env
    with patch(
        "octop.api.routers.providers.fetch_openai_compatible_models", new=AsyncMock()
    ) as remote:
        r = await client.post(
            "/api/admin/providers/fetch-models",
            headers=auth,
            json={
                "kind": "openai",
                "name": "A renamed package",
                "preset_id": preset_id,
                "base_url": "https://api.lkeap.cloud.tencent.com/plan/v3",
            },
        )
    assert r.status_code == 200, r.text
    ids = [m["id"] for m in r.json()["models"]]
    if preset_id == "tencent-hy-token-plan":
        assert ids == ["hy4", "hy3", "hy3-preview"]
    else:
        assert "glm-5" in ids and "hy3" not in ids
    remote.assert_not_awaited()


async def test_existing_package_is_scoped_and_display_order_preserves_default(env: Any) -> None:
    client, srv, auth = env
    name = "Tencent Cloud Hy Token Plan"
    pid = srv.services.provider_repo.create(
        name=name,
        kind="openai",
        base_url="https://example.test/v1",
        api_key="test-key",
        models_json=json.dumps(
            [
                {"id": "hy3", "name": "My Hy3", "enabled": True},
                {"id": "glm-5", "name": "Foreign", "enabled": True},
                {"id": "hy4", "name": "Hy4", "enabled": False},
            ]
        ),
    )
    listed = await client.get("/api/admin/providers", headers=auth)
    row = next(p for p in listed.json() if p["id"] == pid)
    assert [m["id"] for m in row["models"]] == ["hy4", "hy3"]
    assert row["default_model"] == "hy3"
    assert row["preset_id"] == "tencent-hy-token-plan"
    assert row["model_catalog_locked"] is True

    # Saving the display order must not silently choose HY4 as the default.
    row["models"][0]["enabled"] = True
    row["models"].append({"id": "glm-5", "name": "Foreign", "enabled": True})
    saved = await client.patch(
        f"/api/admin/providers/{pid}", headers=auth, json={"models": row["models"]}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["default_model"] == "hy3"
    stored = srv.services.provider_repo.get(pid).get_models()
    assert [m["id"] for m in stored] == ["hy3", "hy4"]

    selected = await client.patch(
        f"/api/admin/providers/{pid}", headers=auth, json={"model": "hy4"}
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["default_model"] == "hy4"


async def test_named_package_create_cannot_import_another_packages_models(env: Any) -> None:
    client, srv, auth = env
    r = await client.post(
        "/api/admin/providers",
        headers=auth,
        json={
            "name": "My HY package",
            "kind": "openai",
            "api_key": "test-key",
            "extra_json": json.dumps({"preset_id": "tencent-hy-token-plan"}),
            "models": [
                {"id": "hy4", "name": "Hy4", "enabled": True},
                {"id": "glm-5", "name": "GLM", "enabled": True},
            ],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["preset_id"] == "tencent-hy-token-plan"
    assert [m["id"] for m in r.json()["models"]] == ["hy4"]
    stored = srv.services.provider_repo.get(r.json()["id"]).get_models()
    assert [m["id"] for m in stored] == ["hy4"]
