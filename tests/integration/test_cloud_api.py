"""Cloud workbench authorization: panel permission and per-user tccli import."""

from __future__ import annotations

import json
from pathlib import Path

from tests.support.auth import create_user, resolve_user_id


def _oauth_file(path: Path, *, secret_id: str, expires_at: float) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "oauth",
                "secretId": secret_id,
                "secretKey": "secret-key-value",
                "token": "sts-token",
                "expiresAt": expires_at,
                "oauth": {
                    "openId": "open-id",
                    "accessToken": "access-token",
                    "expiresAt": expires_at,
                    "refreshToken": "refresh-token",
                    "site": "cn",
                },
            }
        )
    )


async def test_cloud_routes_require_workbench_permission(env, tmp_path: Path, monkeypatch):
    client, _, admin = env
    plain = await create_user(client, admin, username="cloud-plain", permissions=[])
    browser_only = await create_user(
        client, admin, username="cloud-browser", permissions=["browser"]
    )
    workbench = await create_user(client, admin, username="cloud-user", permissions=["cloud"])
    denied_status = await client.get("/api/cloud/status", headers=plain)
    assert denied_status.status_code == 403
    denied_browser = await client.get("/api/cloud/status", headers=browser_only)
    assert denied_browser.status_code == 403
    denied_import = await client.post("/api/cloud/import-from-tccli", headers=plain)
    assert denied_import.status_code == 403
    denied_action = await client.post(
        "/api/cloud/action",
        headers=plain,
        json={"region": "ap-guangzhou", "instance_id": "ins-test", "action": "stop"},
    )
    assert denied_action.status_code == 403

    tccli = tmp_path / ".tccli"
    tccli.mkdir()
    _oauth_file(tccli / "default.credential", secret_id="AKIDshared", expires_at=111.0)
    uid = await resolve_user_id(client, admin, "cloud-user")
    own_expires = 1893456000.0
    _oauth_file(
        tccli / f"octop-{uid}.credential",
        secret_id="AKIDown",
        expires_at=own_expires,
    )
    monkeypatch.setattr("octop.infra.cloud.tencent.Path.home", lambda: tmp_path)

    missing = await client.get("/api/cloud/status", headers=workbench)
    assert missing.status_code == 200
    assert missing.json()["authorized"] is False

    imported = await client.post("/api/cloud/import-from-tccli", headers=workbench)
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["authorized"] is True
    assert body["expires_at"] == own_expires
