"""Composer capture uses the existing authenticated attachment pipeline."""

from dataclasses import asdict

import pytest

from octop.api.routers import uploads
from octop.infra.gateway.media.inbound_store import write_inbound
from tests.support.auth import auth_header, create_user


@pytest.mark.parametrize("mode", ["scan", "photo", "album"])
async def test_capture_returns_previewable_pending_attachment(env_with_agent, monkeypatch, mode):
    client, _server, auth, aid = env_with_agent

    async def scan(workspace, selected_mode="scan", *, max_bytes=None):
        assert selected_mode == mode
        stored = await write_inbound(
            workspace, b"%PDF-original", filename="scan.pdf", media_type="application/pdf"
        )
        preview = await write_inbound(
            workspace, b"preview-png", filename="preview.png", media_type="image/png"
        )
        return {"status": "ok", "files": [{**asdict(stored), "preview_path": preview.path}]}

    monkeypatch.setattr(uploads, "capture_from_composer", scan)
    response = await client.post(
        f"/api/agents/{aid}/native-capture", headers=auth, json={"mode": mode}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ok"
    attachment = result["attachments"][0]
    assert attachment["workspace_path"].startswith("inbound/")
    download = await client.get(attachment["access_url"], headers=auth)
    assert download.status_code == 200
    assert download.content == b"%PDF-original"
    from octop.api.routers.chat.models import ChatTurnBody
    from octop.api.routers.chat.turn import content_parts_from_dashboard_turn

    parts = content_parts_from_dashboard_turn(
        ChatTurnBody(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "file",
                            "workspace_path": attachment["workspace_path"],
                            "filename": attachment["filename"],
                            "media_type": attachment["media_type"],
                        }
                    ],
                }
            ]
        )
    )
    assert parts[-1].local_path == attachment["workspace_path"]
    preview = await client.get(attachment["preview_url"], headers=auth)
    assert preview.status_code == 200
    assert preview.content == b"preview-png"
    assert (await client.get(attachment["preview_url"])).status_code == 401
    schema = client._transport.app.openapi()
    for method in ("get", "post"):
        route = schema["paths"]["/api/agents/{agent_id}/native-capture"][method]
        assert route["summary"]
        assert "$ref" in route["responses"]["200"]["content"]["application/json"]["schema"]


async def test_capture_cancel_does_not_create_attachment(env_with_agent, monkeypatch):
    client, _server, auth, aid = env_with_agent

    async def scan(*args, **kwargs):
        return {"status": "cancelled", "files": []}

    monkeypatch.setattr(uploads, "capture_from_composer", scan)
    response = await client.post(f"/api/agents/{aid}/native-capture", headers=auth)
    assert response.json() == {"status": "cancelled", "attachments": []}


async def test_capture_rejects_another_user_before_launch(env_with_agent, monkeypatch):
    client, _server, auth, aid = env_with_agent
    await create_user(client, auth, username="capture-other")
    other = await auth_header(client, username="capture-other")

    async def never(*args, **kwargs):
        raise AssertionError("must not launch native UI")

    monkeypatch.setattr(uploads, "capture_from_composer", never)
    response = await client.post(f"/api/agents/{aid}/native-capture", headers=other)
    assert response.status_code == 403
    anonymous = await client.post(f"/api/agents/{aid}/native-capture")
    assert anonymous.status_code == 401
