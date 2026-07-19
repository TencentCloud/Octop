"""Unit tests for inbound attachment LLM hints."""

from __future__ import annotations

import base64
import tempfile

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from harness_agent.backends.workspace import BackendWorkspace
from harness_gateway.models import FileContent, ImageContent, TextContent

from octop.api.routers.chat.models import ChatTurnBody
from octop.api.routers.chat.turn import (
    COMPOSER_CTX_KEY,
    INBOUND_ATTACHMENTS_KEY,
    build_dashboard_inbound,
    content_parts_from_dashboard_turn,
)
from octop.infra.gateway.media.attachment_hints import (
    VISION_MAX_BYTES,
    format_attachment_path_hint,
    hints_from_content_parts,
    inbound_attachments_from_parts,
    materialize_image_part,
)
from octop.infra.gateway.media.inbound_store import (
    resolve_inbound_attachment_path,
    write_inbound,
)
from octop.infra.gateway.media.ingress import AgentBackedMediaBackend
from octop.infra.gateway.process.harness_request import build_content_from_message
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.gateway.ws import WS_CHANNEL_ID


def _workspace(root: str) -> BackendWorkspace:
    backend = LocalShellBackend(root_dir=root, virtual_mode=False)
    return BackendWorkspace(backend, root)


def test_hints_from_file_content() -> None:
    parts = [
        TextContent(text="summarize"),
        FileContent(
            filename="report.pdf",
            mime_type="application/pdf",
            local_path="dingtalk/ch1/123_report.pdf",
            size=1024,
        ),
        ImageContent(url="http://example.com/x.png"),
    ]
    hints = hints_from_content_parts(parts)
    assert len(hints) == 1
    assert "inbound/dingtalk/ch1/123_report.pdf" in hints[0]


@pytest.mark.asyncio
async def test_hints_from_file_content_with_workspace_resolve_path() -> None:
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = _workspace(ws_dir)
        stored = await write_inbound(
            workspace,
            b"%PDF-1.4",
            filename="report.pdf",
            media_type="application/pdf",
        )
        parts = [
            FileContent(
                filename="report.pdf",
                mime_type="application/pdf",
                local_path=stored.path,
                size=1024,
            ),
        ]
        hints = hints_from_content_parts(parts, workspace=workspace)
        resolved = resolve_inbound_attachment_path(workspace, stored.path)
        assert len(hints) == 1
        assert f"Workspace path: {resolved}" in hints[0] or f"工作区路径：{resolved}" in hints[0]


def test_format_pdf_hint() -> None:
    text = format_attachment_path_hint(
        filename="a.pdf",
        path="inbound/x.pdf",
        media_type="application/pdf",
    )
    assert "pdf" in text.lower()
    assert "[附件]" in text or "Attachment" in text


@pytest.mark.asyncio
async def test_materialize_image_part_from_workspace_path() -> None:
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = _workspace(ws_dir)
        stored = await write_inbound(
            workspace,
            b"png-bytes",
            filename="shot.png",
            media_type="image/png",
        )
        backend = AgentBackedMediaBackend(workspace)
        part = ImageContent(local_path=stored.path, mime_type="image/png")
        block = await materialize_image_part(part, media_backend=backend, workspace=workspace)
        assert block is not None
        assert block["type"] == "image_url"
        url = block["image_url"]["url"]
        assert url.startswith("data:image/png;base64,")
        assert base64.b64decode(url.split(",", 1)[1]) == b"png-bytes"
        assert block["workspace_path"] == stored.path


@pytest.mark.asyncio
async def test_file_typed_image_path_still_materializes_via_content_parts() -> None:
    """Dashboard mis-tagged type:file with image mime → ImageContent → vision."""
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = _workspace(ws_dir)
        stored = await write_inbound(
            workspace,
            b"png-bytes",
            filename="paste.png",
            media_type="image/png",
        )
        turn = ChatTurnBody(
            text="what",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "what"},
                        {
                            "type": "file",
                            "workspace_path": stored.path,
                            "filename": "paste.png",
                            "media_type": "image/png",
                        },
                    ],
                }
            ],
        )
        parts = content_parts_from_dashboard_turn(turn)
        assert any(isinstance(p, ImageContent) for p in parts)
        backend = AgentBackedMediaBackend(workspace)
        from harness_gateway.models import InboundMessage

        msg = InboundMessage(
            channel_id=WS_CHANNEL_ID,
            channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            content=parts,
        )
        content = await build_content_from_message(msg, media_backend=backend)
        assert isinstance(content, list)
        img = next(b for b in content if b.get("type") == "image_url")
        assert base64.b64decode(img["image_url"]["url"].split(",", 1)[1]) == b"png-bytes"


@pytest.mark.asyncio
async def test_oversized_image_degrades_to_path_hint() -> None:
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = _workspace(ws_dir)
        big = b"x" * (VISION_MAX_BYTES + 1)
        stored = await write_inbound(
            workspace,
            big,
            filename="huge.png",
            media_type="image/png",
        )
        backend = AgentBackedMediaBackend(workspace)
        part = ImageContent(local_path=stored.path, mime_type="image/png", size=len(big))
        block = await materialize_image_part(part, media_backend=backend, workspace=workspace)
        assert block is not None
        assert block["type"] == "text"
        hint = block["text"].replace("\\", "/")
        assert stored.path.replace("\\", "/") in hint or "inbound/" in hint


def test_inbound_attachments_from_parts() -> None:
    parts = [
        TextContent(text="see"),
        ImageContent(local_path="inbound/01KWB9MG2Z570P7QB367KDJ75R.png", mime_type="image/png"),
        FileContent(
            local_path="inbound/01KWB9MG2Z570P7QB367KDJ75R.pdf",
            filename="report.pdf",
            mime_type="application/pdf",
        ),
    ]
    extracted = inbound_attachments_from_parts(parts)
    assert len(extracted) == 2
    assert extracted[0]["kind"] == "image"
    assert extracted[0]["workspace_path"] == "inbound/01KWB9MG2Z570P7QB367KDJ75R.png"
    assert "file_id" not in extracted[0]
    assert extracted[1]["kind"] == "file"


def test_build_dashboard_inbound_uses_content_parts_not_messages_meta() -> None:
    from octop.api.routers.chat.turn import PreparedDashboardTurn

    parts = [
        TextContent(text="hi"),
        FileContent(
            local_path="inbound/x.pdf",
            filename="x.pdf",
            mime_type="application/pdf",
        ),
    ]
    prepared = PreparedDashboardTurn(
        thread_id="t1",
        session_key="sk",
        mcp_servers=None,
        skills=None,
        model_ref=None,
        inbound_content=parts,
        composer_context={"skills": ["pdf"]},
        inbound_attachments=inbound_attachments_from_parts(parts),
    )
    inbound = build_dashboard_inbound(
        agent_id="agent-1",
        user_id=1,
        prepared=prepared,
        turn=ChatTurnBody(text="hi"),
        ws_connection_id="conn",
    )
    assert "messages" not in inbound.metadata
    assert inbound.metadata[COMPOSER_CTX_KEY] == {"skills": ["pdf"]}
    assert INBOUND_ATTACHMENTS_KEY in inbound.metadata
    assert any(isinstance(p, FileContent) for p in inbound.content)


def test_serialize_history_exposes_inbound_attachments() -> None:
    from langchain_core.messages import HumanMessage

    from octop.api.routers.chat.serialize import _serialize_history_message

    attachments = [
        {
            "workspace_path": "inbound/01KWB9MG2Z570P7QB367KDJ75R.png",
            "filename": "shot.png",
            "media_type": "image/png",
            "kind": "image",
        }
    ]
    msg = HumanMessage(
        content=[{"type": "text", "text": "hi"}],
        additional_kwargs={INBOUND_ATTACHMENTS_KEY: attachments},
    )
    entry = _serialize_history_message(msg)
    assert entry is not None
    assert entry["inbound_attachments"] == attachments


def test_content_blocks_need_vision_detects_image_url() -> None:
    from octop.infra.gateway.media.attachment_hints import content_blocks_need_vision

    content = [
        {"type": "text", "text": "what is this?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
    ]
    assert content_blocks_need_vision(content) is True
    assert content_blocks_need_vision("hello") is False
