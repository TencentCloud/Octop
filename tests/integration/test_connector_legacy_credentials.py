"""Legacy encrypted TEXT credentials remain usable through the HTTP surface."""

from __future__ import annotations

from octop.infra.connectors.service import ConnectorService
from tests.support.auth import resolve_user_id


async def test_legacy_text_credentials_do_not_break_connector_http_list(env):
    client, server, auth = env
    owner_id = await resolve_user_id(client, auth, "admin")
    services = server.services
    svc = ConnectorService(
        repo=services.connector_repo,
        secret_repo=services.secret_repo,
        settings_repo=services.settings_repo,
        config=services.config,
    )
    response = await client.post(
        "/api/connector-instances",
        headers=auth,
        json={
            "kind": "tencent-docs",
            "display_name": "healthy",
            "credentials": {"token": "fixture-token"},
        },
    )
    assert response.status_code == 201
    svc.put_custom_servers(owner_id, {"legacy": {"transport": "stdio", "command": "fixture-mcp"}})
    parent = services.connector_repo.get_by_user_kind(owner_id, "custom-mcp")
    assert parent is not None and parent.credential_blob is not None
    with services.db.transaction() as conn:
        conn.execute(
            "UPDATE connectors SET credential_blob = ? WHERE instance_id = ?",
            (parent.credential_blob.decode("ascii"), parent.instance_id),
        )

    listed = await client.get("/api/connector-instances", headers=auth)
    assert listed.status_code == 200
    assert {row["display_name"] for row in listed.json()} == {"healthy", "legacy"}
    custom = await client.get("/api/connectors/custom-mcp", headers=auth)
    assert custom.status_code == 200
    assert "fixture-mcp" in custom.text
    assert "fixture-token" not in listed.text
    assert parent.credential_blob.decode("ascii") not in listed.text + custom.text
