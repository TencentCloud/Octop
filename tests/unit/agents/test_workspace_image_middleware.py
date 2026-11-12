"""Unit tests for WorkspaceImageMaterializeMiddleware."""

from __future__ import annotations

import base64
import io
import tempfile
from typing import Any
from unittest.mock import MagicMock

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from langchain_core.messages import HumanMessage
from octop_harness.backends.workspace import BackendWorkspace
from PIL import Image

from octop.api.common.attachments import save_attachment
from octop.infra.agents.middleware.workspace_image import WorkspaceImageMaterializeMiddleware
from octop.infra.gateway.media.attachment_hints import (
    VISION_SAFE_MAX_SIDE,
    make_image_url_block,
    make_workspace_image_ref,
)

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.mark.asyncio
async def test_awrap_model_call_expands_workspace_image_ref() -> None:
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
        ref = make_workspace_image_ref(workspace_path=stored.data_path, mime_type="image/png")
        human = HumanMessage(content=[{"type": "text", "text": "see"}, ref])
        captured: dict[str, Any] = {}

        async def handler(request: Any) -> Any:
            captured["messages"] = request.messages
            return MagicMock()

        request = MagicMock()
        request.messages = [human]
        request.override = lambda **kw: MagicMock(messages=kw["messages"])

        mw = WorkspaceImageMaterializeMiddleware(workspace=workspace)
        await mw.awrap_model_call(request, handler)

        expanded = captured["messages"][0].content[1]
        url = expanded["image_url"]["url"]
        assert url.startswith("data:image/png;base64,")
        assert base64.b64decode(url.split(",", 1)[1]) == _PNG
        # Original checkpoint message is unchanged.
        assert human.content[1]["image_url"]["url"].startswith("workspace://")


@pytest.mark.asyncio
async def test_text_only_message_is_not_copied() -> None:
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = BackendWorkspace(
            LocalShellBackend(root_dir=ws_dir, virtual_mode=False),
            ws_dir,
        )
        human = HumanMessage(content=[{"type": "text", "text": "hello"}])
        captured: dict[str, Any] = {}

        async def handler(request: Any) -> Any:
            captured["messages"] = request.messages
            return MagicMock()

        request = MagicMock()
        request.messages = [human]
        request.override = lambda **kw: MagicMock(messages=kw["messages"])

        mw = WorkspaceImageMaterializeMiddleware(workspace=workspace)
        await mw.awrap_model_call(request, handler)
        assert captured["messages"][0] is human


@pytest.mark.asyncio
async def test_historical_long_data_url_is_fitted_without_mutating_checkpoint() -> None:
    img = Image.new("RGB", (32, VISION_SAFE_MAX_SIDE + 1000), (20, 40, 60))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    raw = buf.getvalue()
    original = make_image_url_block(base64.b64encode(raw).decode(), "image/jpeg")
    human = HumanMessage(content=[{"type": "text", "text": "next"}, original])
    captured: dict[str, Any] = {}

    async def handler(request: Any) -> Any:
        captured["messages"] = request.messages
        return MagicMock()

    request = MagicMock()
    request.messages = [human]
    request.override = lambda **kw: MagicMock(messages=kw["messages"])

    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = BackendWorkspace(
            LocalShellBackend(root_dir=ws_dir, virtual_mode=False),
            ws_dir,
        )
        mw = WorkspaceImageMaterializeMiddleware(workspace=workspace)
        await mw.awrap_model_call(request, handler)

    outgoing = captured["messages"][0].content[1]["image_url"]["url"]
    fitted = base64.b64decode(outgoing.split(",", 1)[1])
    with Image.open(io.BytesIO(fitted)) as out:
        assert max(out.size) <= VISION_SAFE_MAX_SIDE
    stored = human.content[1]["image_url"]["url"]
    assert stored == original["image_url"]["url"]
    assert stored != outgoing
