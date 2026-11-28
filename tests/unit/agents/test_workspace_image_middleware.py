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


def _fake_image_invalid_400() -> Exception:
    import httpx
    from openai import BadRequestError

    req = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    resp = httpx.Response(400, request=req)
    body = {
        "error": {
            "code": "image_invalid",
            "gateway_hint": "image data rejected by upstream; use a real/valid image",
            "message": "extError code 1210, code 11135, Please start a new conversation",
        }
    }
    return BadRequestError(
        "Error code: 400 - image_invalid extError code 1210, code 11135",
        response=resp,
        body=body,
    )


@pytest.mark.asyncio
async def test_image_invalid_400_retries_without_images_and_sanitizes_after_model() -> None:
    from langgraph.graph.message import add_messages

    from octop.infra.gateway.process.message_keys import INBOUND_ATTACHMENTS_KEY

    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = BackendWorkspace(
            LocalShellBackend(root_dir=ws_dir, virtual_mode=False),
            ws_dir,
        )
        stored = await save_attachment(
            workspace,
            owner_id=1,
            filename="bad.jpg",
            media_type="image/jpeg",
            data=_PNG,
        )
        ref = make_workspace_image_ref(workspace_path=stored.data_path, mime_type="image/jpeg")
        attachments_meta = [{"kind": "image", "workspace_path": stored.data_path}]
        human = HumanMessage(
            id="msg-bad-img",
            content=[{"type": "text", "text": "what is this?"}, ref],
            additional_kwargs={INBOUND_ATTACHMENTS_KEY: attachments_meta},
        )
        seen_contents: list[Any] = []

        async def handler(request: Any) -> Any:
            seen_contents.append(request.messages[0].content)
            if len(seen_contents) == 1:
                raise _fake_image_invalid_400()
            return MagicMock()

        request = MagicMock()
        request.messages = [human]
        request.runtime = MagicMock()
        request.runtime.config = {"configurable": {"thread_id": "thr-1"}}
        request.runtime.configurable = None
        request.runtime.context = None
        request.override = lambda **kw: MagicMock(
            messages=kw["messages"],
            runtime=request.runtime,
        )

        mw = WorkspaceImageMaterializeMiddleware(workspace=workspace, locale="zh")
        await mw.awrap_model_call(request, handler)

        assert len(seen_contents) == 2
        assert seen_contents[0][1]["type"] == "image_url"
        assert seen_contents[1][1] == {"type": "text", "text": "[图片无法识别，已忽略]"}
        assert stored.data_path not in str(seen_contents[1])

        # Thread isolation: another thread does not pop thr-1's pending cleanup.
        other_runtime = MagicMock()
        other_runtime.config = {"configurable": {"thread_id": "thr-other"}}
        assert await mw.aafter_model({"messages": [human]}, other_runtime) is None

        update = await mw.aafter_model({"messages": [human]}, request.runtime)
        assert update is not None
        merged = add_messages([human], update["messages"])
        assert len(merged) == 1
        assert merged[0].id == "msg-bad-img"
        assert merged[0].content == [
            {"type": "text", "text": "what is this?"},
            {"type": "text", "text": "[图片无法识别，已忽略]"},
        ]
        assert merged[0].additional_kwargs[INBOUND_ATTACHMENTS_KEY] == attachments_meta
        assert await mw.aafter_model({"messages": merged}, request.runtime) is None


@pytest.mark.asyncio
async def test_non_image_400_or_text_only_400_is_not_retried() -> None:
    import httpx
    from openai import BadRequestError

    req = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    resp = httpx.Response(400, request=req)
    non_image_400 = BadRequestError(
        "invalid tool schema",
        response=resp,
        body={"error": {"code": "invalid_request"}},
    )

    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = BackendWorkspace(
            LocalShellBackend(root_dir=ws_dir, virtual_mode=False),
            ws_dir,
        )
        mw = WorkspaceImageMaterializeMiddleware(workspace=workspace)

        img_block = make_image_url_block(base64.b64encode(_PNG).decode(), "image/png")
        img_msg = HumanMessage(id="m1", content=[{"type": "text", "text": "hi"}, img_block])
        req1 = MagicMock()
        req1.messages = [img_msg]
        req1.runtime = None
        req1.override = lambda **kw: MagicMock(messages=kw["messages"], runtime=None)
        calls1 = 0

        async def h1(_r: Any) -> Any:
            nonlocal calls1
            calls1 += 1
            raise non_image_400

        with pytest.raises(BadRequestError):
            await mw.awrap_model_call(req1, h1)
        assert calls1 == 1

        text_msg = HumanMessage(id="m2", content=[{"type": "text", "text": "text only"}])
        req2 = MagicMock()
        req2.messages = [text_msg]
        req2.runtime = None
        req2.override = lambda **kw: MagicMock(messages=kw["messages"], runtime=None)
        calls2 = 0

        async def h2(_r: Any) -> Any:
            nonlocal calls2
            calls2 += 1
            raise _fake_image_invalid_400()

        with pytest.raises(BadRequestError):
            await mw.awrap_model_call(req2, h2)
        assert calls2 == 1


@pytest.mark.asyncio
async def test_failed_fallback_retry_does_not_queue_after_model_sanitization() -> None:
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = BackendWorkspace(
            LocalShellBackend(root_dir=ws_dir, virtual_mode=False),
            ws_dir,
        )
        mw = WorkspaceImageMaterializeMiddleware(workspace=workspace)
        img_block = make_image_url_block(base64.b64encode(_PNG).decode(), "image/png")
        msg = HumanMessage(id="m-fail", content=[{"type": "text", "text": "see"}, img_block])
        runtime = MagicMock()
        runtime.config = {"configurable": {"thread_id": "thr-fail"}}
        runtime.configurable = None
        runtime.context = None
        req = MagicMock()
        req.messages = [msg]
        req.runtime = runtime
        req.override = lambda **kw: MagicMock(messages=kw["messages"], runtime=runtime)

        calls = 0

        async def handler(_r: Any) -> Any:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise _fake_image_invalid_400()
            raise RuntimeError("upstream down on fallback")

        with pytest.raises(RuntimeError, match="upstream down on fallback"):
            await mw.awrap_model_call(req, handler)
        assert calls == 2
        assert await mw.aafter_model({"messages": [msg]}, runtime) is None
