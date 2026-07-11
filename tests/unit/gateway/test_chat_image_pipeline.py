"""End-to-end attachment pipeline tests (no WebSocket — direct API calls)."""

from __future__ import annotations

import base64
import re
import tempfile
from pathlib import Path
from typing import Any

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from harness_agent.backends.workspace import BackendWorkspace
from harness_gateway.models import InboundMessage

from octop.api.common.attachments import save_attachment
from octop.api.routers.chat.models import ChatTurnBody
from octop.api.routers.chat.turn import (
    content_parts_from_dashboard_turn,
)
from octop.infra.backend.resolver import default_agent_backend_spec
from octop.infra.gateway.media.attachment_hints import content_blocks_need_vision
from octop.infra.gateway.media.ingress import AgentBackedMediaBackend
from octop.infra.gateway.process.harness_request import build_content_from_message
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.gateway.ws import WS_CHANNEL_ID

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _has_image_url(content: Any) -> bool:
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "image_url" for b in content
    )


def _image_bytes(content: Any) -> bytes | None:
    if not isinstance(content, list):
        return None
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "image_url":
            continue
        url_field = block.get("image_url") or {}
        url = url_field.get("url") if isinstance(url_field, dict) else None
        if isinstance(url, str) and ";base64," in url:
            return base64.b64decode(url.split(",", 1)[1])
    return None


@pytest.mark.asyncio
async def test_file_in_workspace_with_workspace_path_reaches_llm() -> None:
    """Upload → turn with workspace_path → harness content has image_url base64."""
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = BackendWorkspace(
            LocalShellBackend(root_dir=ws_dir, virtual_mode=False),
            ws_dir,
        )
        stored = await save_attachment(
            workspace,
            owner_id=1,
            filename="chart.png",
            media_type="image/png",
            data=_PNG,
        )
        assert stored.data_path.startswith("inbound/")
        assert re.search(r"inbound/\d{10,}_chart\.png$", stored.data_path)
        assert await workspace.adownload_bytes(stored.data_path) == _PNG

        preview = f"/api/agents/agent-1/media/preview?source={stored.data_path}"
        turn = ChatTurnBody(
            text="what is this?",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "what is this?"},
                        {
                            "type": "image",
                            "source": {"type": "url", "url": preview, "media_type": "image/png"},
                            "preview_url": preview,
                            "workspace_path": stored.data_path,
                            "filename": "chart.png",
                        },
                    ],
                }
            ],
        )
        parts = content_parts_from_dashboard_turn(turn)
        assert any(getattr(p, "local_path", None) == stored.data_path for p in parts)

        msg = InboundMessage(
            channel_id=WS_CHANNEL_ID,
            channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            content=parts,
        )
        backend = AgentBackedMediaBackend(workspace)
        content = await build_content_from_message(msg, media_backend=backend)
        assert _has_image_url(content)
        assert content_blocks_need_vision(content)
        assert _image_bytes(content) == _PNG


@pytest.mark.asyncio
async def test_file_in_workspace_preview_only_drops_image_for_llm() -> None:
    """File exists in workspace but turn lacks workspace_path → no vision for LLM."""
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = BackendWorkspace(
            LocalShellBackend(root_dir=ws_dir, virtual_mode=False),
            ws_dir,
        )
        stored = await save_attachment(
            workspace,
            owner_id=1,
            filename="shot.png",
            media_type="image/png",
            data=_PNG,
        )
        assert await workspace.adownload_bytes(stored.data_path) == _PNG

        preview = f"/api/agents/agent-1/media/preview?source={stored.data_path}"
        turn = ChatTurnBody(
            text="describe",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "describe"},
                        {
                            "type": "image",
                            "source": {"type": "url", "url": preview, "media_type": "image/png"},
                            "preview_url": preview,
                        },
                    ],
                }
            ],
        )
        parts = content_parts_from_dashboard_turn(turn)
        assert not any(getattr(p, "local_path", None) for p in parts)

        msg = InboundMessage(
            channel_id=WS_CHANNEL_ID,
            channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            content=parts,
        )
        backend = AgentBackedMediaBackend(workspace)
        content = await build_content_from_message(msg, media_backend=backend)
        assert not _has_image_url(content)
        assert not content_blocks_need_vision(content)


@pytest.mark.asyncio
async def test_default_backend_materialize_still_inlines_image() -> None:
    """Production default backend: vision materialize via BackendWorkspace still works."""
    from harness_agent.backends import resolve_backend

    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = BackendWorkspace(
            resolve_backend(default_agent_backend_spec(Path(ws_dir)), workspace_dir=ws_dir),
            ws_dir,
        )
        stored = await save_attachment(
            workspace,
            owner_id=1,
            filename="chart.png",
            media_type="image/png",
            data=_PNG,
        )
        assert await workspace.adownload_bytes(stored.data_path) == _PNG

        turn = ChatTurnBody(
            text="see",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "workspace_path": stored.data_path,
                            "media_type": "image/png",
                            "filename": "chart.png",
                        },
                    ],
                }
            ],
        )
        parts = content_parts_from_dashboard_turn(turn)
        msg = InboundMessage(
            channel_id=WS_CHANNEL_ID,
            channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            content=parts,
        )
        content = await build_content_from_message(
            msg,
            media_backend=AgentBackedMediaBackend(workspace),
        )
        assert _has_image_url(content)
        assert _image_bytes(content) == _PNG


@pytest.mark.asyncio
async def test_no_media_backend_degrades_to_path_hint_not_vision() -> None:
    """Agent stopped (media_backend=None): file readable but LLM gets text hint only."""
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = BackendWorkspace(
            LocalShellBackend(root_dir=ws_dir, virtual_mode=False),
            ws_dir,
        )
        stored = await save_attachment(
            workspace,
            owner_id=1,
            filename="chart.png",
            media_type="image/png",
            data=_PNG,
        )
        turn = ChatTurnBody(
            text="see",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "workspace_path": stored.data_path,
                            "media_type": "image/png",
                        },
                    ],
                }
            ],
        )
        parts = content_parts_from_dashboard_turn(turn)
        msg = InboundMessage(
            channel_id=WS_CHANNEL_ID,
            channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            content=parts,
        )
        content = await build_content_from_message(msg, media_backend=None)
        assert not _has_image_url(content)
        assert isinstance(content, str)
        assert stored.data_path in content or "inbound/" in content
