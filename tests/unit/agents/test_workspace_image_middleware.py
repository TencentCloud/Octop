"""Unit tests for WorkspaceImageMaterializeMiddleware."""

from __future__ import annotations

import base64
import tempfile
from typing import Any
from unittest.mock import MagicMock

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from harness_agent.backends.workspace import BackendWorkspace
from langchain_core.messages import HumanMessage

from octop.api.common.attachments import save_attachment
from octop.infra.agents.middleware.workspace_image import WorkspaceImageMaterializeMiddleware
from octop.infra.gateway.media.attachment_hints import make_workspace_image_ref

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
