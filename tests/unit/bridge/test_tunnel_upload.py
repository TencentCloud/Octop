"""Chat attachments cross the bridge as a tunneled multipart upload."""

from __future__ import annotations

import asyncio
import base64
import json

import pytest
from fastapi import FastAPI, File, UploadFile

from octop.infra.bridge.http_tunnel import execute_local_http
from octop.infra.bridge.ids import rewrite_tunneled_json
from octop.infra.bridge.transport import (
    BODY_CHUNK_RAW_BYTES,
    FEATURE_BODY_CHUNKS,
    BridgeSession,
)


def _multipart(filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = "----octop-bridge"
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: text/plain\r\n\r\n"
        ).encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return body, f"multipart/form-data; boundary={boundary}"


@pytest.mark.asyncio
async def test_execute_local_http_accepts_chat_upload() -> None:
    app = FastAPI()

    @app.post("/api/agents/{agent_id}/upload")
    async def upload(agent_id: str, file: UploadFile = File(...)) -> dict[str, object]:  # noqa: B008
        data = await file.read()
        return {
            "path": f"inbound/{file.filename}",
            "workspace_path": f"inbound/{file.filename}",
            "filename": file.filename,
            "media_type": file.content_type,
            "url": f"/api/agents/{agent_id}/media/preview?source=inbound/{file.filename}",
            "access_url": f"/api/agents/{agent_id}/media/preview?source=inbound/{file.filename}",
            "size": len(data),
        }

    raw, content_type = _multipart("note.txt", b"hello-bridge")
    result = await execute_local_http(
        app=app,
        method="POST",
        path="/api/agents/doctor/upload",
        headers={"content-type": content_type},
        body=raw,
        access_token="token",
    )
    assert result["status"] == 200
    payload = json.loads(base64.b64decode(str(result["body_b64"])))
    rewritten = rewrite_tunneled_json(
        payload,
        remote_agent_id="doctor",
        bridge_agent_id="bridge:cid1:doctor",
    )
    assert rewritten["filename"] == "note.txt"
    assert rewritten["path"] == "inbound/note.txt"
    assert rewritten["url"].startswith("/api/agents/bridge:cid1:doctor/media/preview")


@pytest.mark.asyncio
async def test_chunked_upload_body_is_reassembled() -> None:
    captured: dict[str, object] = {}

    async def on_request(payload: dict[str, object]) -> dict[str, object]:
        from octop.infra.bridge.http_tunnel import decode_body_b64

        captured["body"] = decode_body_b64(payload)
        captured["path"] = payload.get("path")
        captured["content_type"] = (payload.get("headers") or {}).get("content-type")  # type: ignore[union-attr]
        return {"status": 201, "headers": {"content-type": "application/json"}, "done": True}

    peer: BridgeSession
    initiator: BridgeSession

    async def peer_send(text: str) -> None:
        await initiator.handle_message(text)

    async def initiator_send(text: str) -> None:
        await peer.handle_message(text)

    peer = BridgeSession(
        connection_id="cid",
        send_text=peer_send,
        on_tunnel_request=on_request,
        peer_features={FEATURE_BODY_CHUNKS},
    )
    initiator = BridgeSession(
        connection_id="cid",
        send_text=initiator_send,
        peer_features={FEATURE_BODY_CHUNKS},
    )
    raw, content_type = _multipart("blob.bin", b"a" * (BODY_CHUNK_RAW_BYTES + 32))
    result = await initiator.tunnel_request(
        method="POST",
        path="/api/agents/doctor/upload",
        headers={"content-type": content_type},
        body=raw,
    )
    assert result["status"] == 201
    assert captured["body"] == raw
    assert captured["path"] == "/api/agents/doctor/upload"
    assert captured["content_type"] == content_type
    await asyncio.gather(peer.close(), initiator.close())


def _chunk_frame(req_id: str, seq: int, piece: bytes, *, more: bool) -> dict[str, object]:
    """One ``tunnel.request`` frame as a peer would put on the wire."""
    return {
        "type": "tunnel.request",
        "id": req_id,
        "method": "POST",
        "path": "/api/agents/doctor/upload",
        "body_seq": seq,
        "body_more": more,
        "body_b64": base64.b64encode(piece).decode("ascii"),
    }


@pytest.mark.asyncio
async def test_chunked_body_over_cap_is_rejected_without_buffering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sender-side cap is a client-side check; reassembly must hold the line.

    ``tunnel_http`` only refuses an oversized body before it is sent, so a peer
    that streams its own frames used to be buffered without limit.
    """
    from octop.infra.bridge import transport as bridge_transport

    monkeypatch.setattr(bridge_transport, "BRIDGE_TUNNEL_CHUNKED_MAX_BODY_BYTES", 64 * 1024)

    handled: list[dict[str, object]] = []
    sent: list[str] = []

    async def on_request(payload: dict[str, object]) -> dict[str, object]:
        handled.append(payload)
        return {"status": 201, "headers": {}, "done": True}

    async def send(text: str) -> None:
        sent.append(text)

    session = bridge_transport.BridgeSession(
        connection_id="cid",
        send_text=send,
        on_tunnel_request=on_request,
    )
    piece = b"z" * (32 * 1024)
    for seq in range(6):
        await session.handle_message(json.dumps(_chunk_frame("big", seq, piece, more=seq < 5)))
    await asyncio.sleep(0)

    assert handled == []
    assert session._body_parts == {}
    frame = json.loads(sent[-1])
    assert frame["type"] == "tunnel.error"
    assert frame["id"] == "big"
    assert frame["code"] == "ATTACHMENT_TOO_LARGE"
    await session.close()


@pytest.mark.asyncio
async def test_missing_chunk_is_rejected_not_spliced() -> None:
    """A gap in the stream must not reach the handler as a shorter, valid-looking body."""
    from octop.infra.bridge import transport as bridge_transport

    handled: list[dict[str, object]] = []
    sent: list[str] = []

    async def on_request(payload: dict[str, object]) -> dict[str, object]:
        handled.append(payload)
        return {"status": 201, "headers": {}, "done": True}

    async def send(text: str) -> None:
        sent.append(text)

    session = bridge_transport.BridgeSession(
        connection_id="cid",
        send_text=send,
        on_tunnel_request=on_request,
    )
    await session.handle_message(json.dumps(_chunk_frame("gap", 0, b"first-", more=True)))
    await session.handle_message(json.dumps(_chunk_frame("gap", 2, b"third", more=False)))
    await asyncio.sleep(0)

    assert handled == []
    assert session._body_parts == {}
    frame = json.loads(sent[-1])
    assert frame["type"] == "tunnel.error"
    assert frame["code"] == "BRIDGE_TUNNEL_FAILED"
    await session.close()


@pytest.mark.asyncio
async def test_abandoned_chunked_body_is_forgotten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An upload the peer walked away from stops pinning its bytes on the next frame."""
    from octop.infra.bridge import transport as bridge_transport

    monkeypatch.setattr(bridge_transport, "_BODY_PART_TTL_SEC", -1.0)

    async def on_request(payload: dict[str, object]) -> dict[str, object]:
        return {"status": 201, "headers": {}, "done": True}

    async def send(text: str) -> None:
        pass

    session = bridge_transport.BridgeSession(
        connection_id="cid",
        send_text=send,
        on_tunnel_request=on_request,
    )
    await session.handle_message(json.dumps(_chunk_frame("orphan", 0, b"x" * 4096, more=True)))
    assert "tunnel.request:orphan" in session._body_parts
    await session.handle_message(json.dumps(_chunk_frame("next", 0, b"y", more=False)))

    assert "tunnel.request:orphan" not in session._body_parts
    await session.close()
