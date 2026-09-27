"""OctopUiOffloadMiddleware: oversized octop_ui payloads move to ToolMessage.artifact."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from octop.infra.agents.middleware.octop_ui_offload import (
    _OFFLOAD_MIN_CHARS,
    OctopUiOffloadMiddleware,
)


def _request() -> MagicMock:
    req = MagicMock()
    req.tool_call = {"name": "bilibili_search_anime", "args": {}, "id": "tc1"}
    return req


def _envelope(data: Any = None) -> dict[str, Any]:
    return {
        "octop_ui": {"renderer": "bilibili_player", "version": 1},
        "data": data,
        "text": "找到 1 部番剧。",
    }


def _big_data() -> dict[str, Any]:
    return {
        "results": [
            {
                "season_id": 1,
                "title": "凡人修仙传",
                "episodes": [
                    {
                        "index": i,
                        "bvid": f"BV1xx4y1z{i:04d}",
                        "long_title": f"第{i}话 标题",
                    }
                    for i in range(1, 201)
                ],
            }
        ]
    }


def _big_message() -> ToolMessage:
    content = json.dumps(_envelope(_big_data()), ensure_ascii=False)
    assert len(content) >= _OFFLOAD_MIN_CHARS
    return ToolMessage(
        content=content,
        tool_call_id="tc1",
        name="bilibili_search_anime",
        id="msg-1",
    )


def test_offloads_oversized_octop_ui_payload_in_place() -> None:
    mw = OctopUiOffloadMiddleware()
    result = _big_message()
    out = mw.wrap_tool_call(_request(), lambda _req: result)

    assert out is result
    # Field preservation (id / tool_call_id / name / status).
    assert out.id == "msg-1"
    assert out.tool_call_id == "tc1"
    assert out.name == "bilibili_search_anime"
    assert out.status == "success"

    envelope = json.loads(out.content)
    assert "data" not in envelope
    assert envelope["data_ref"] == "artifact"
    assert envelope["octop_ui"]["renderer"] == "bilibili_player"
    assert envelope["text"] == "找到 1 部番剧。"
    assert len(out.content) < _OFFLOAD_MIN_CHARS

    artifact = out.artifact
    assert artifact["results"][0]["title"] == "凡人修仙传"
    assert len(artifact["results"][0]["episodes"]) == 200


@pytest.mark.asyncio
async def test_awrap_tool_call_offloads() -> None:
    mw = OctopUiOffloadMiddleware()
    result = _big_message()

    async def handler(_req: Any) -> ToolMessage:
        return result

    out = await mw.awrap_tool_call(_request(), handler)
    assert json.loads(out.content)["data_ref"] == "artifact"
    assert out.artifact["results"]


def test_skips_small_payload() -> None:
    mw = OctopUiOffloadMiddleware()
    content = json.dumps(_envelope({"results": []}), ensure_ascii=False)
    assert len(content) < _OFFLOAD_MIN_CHARS
    result = ToolMessage(content=content, tool_call_id="tc1")
    out = mw.wrap_tool_call(_request(), lambda _req: result)
    assert out.content == content
    assert out.artifact is None


def test_skips_non_json_text() -> None:
    mw = OctopUiOffloadMiddleware()
    content = "x" * (_OFFLOAD_MIN_CHARS + 10)
    result = ToolMessage(content=content, tool_call_id="tc1")
    out = mw.wrap_tool_call(_request(), lambda _req: result)
    assert out.content == content
    assert out.artifact is None


def test_skips_json_without_octop_ui() -> None:
    mw = OctopUiOffloadMiddleware()
    content = json.dumps({"data": {"big": "x" * _OFFLOAD_MIN_CHARS}})
    result = ToolMessage(content=content, tool_call_id="tc1")
    out = mw.wrap_tool_call(_request(), lambda _req: result)
    assert out.content == content
    assert out.artifact is None


def test_skips_octop_ui_without_renderer() -> None:
    mw = OctopUiOffloadMiddleware()
    envelope = _envelope({"big": "x" * _OFFLOAD_MIN_CHARS})
    envelope["octop_ui"] = {"renderer": " "}
    content = json.dumps(envelope)
    result = ToolMessage(content=content, tool_call_id="tc1")
    out = mw.wrap_tool_call(_request(), lambda _req: result)
    assert out.content == content
    assert out.artifact is None


def test_skips_empty_data() -> None:
    mw = OctopUiOffloadMiddleware()
    for empty in (None, {}, []):
        envelope = _envelope(empty)
        envelope["pad"] = "x" * _OFFLOAD_MIN_CHARS
        content = json.dumps(envelope, ensure_ascii=False)
        result = ToolMessage(content=content, tool_call_id="tc1")
        out = mw.wrap_tool_call(_request(), lambda _req, r=result: r)
        assert out.content == content
        assert out.artifact is None


def test_skips_payload_with_file_url() -> None:
    mw = OctopUiOffloadMiddleware()
    data = _big_data()
    data["results"][0]["cover_file"] = "file:///tmp/cover.png"
    content = json.dumps(_envelope(data), ensure_ascii=False)
    result = ToolMessage(content=content, tool_call_id="tc1")
    out = mw.wrap_tool_call(_request(), lambda _req: result)
    assert out.content == content
    assert out.artifact is None


def test_skips_non_string_content_and_command() -> None:
    mw = OctopUiOffloadMiddleware()
    blocks = [{"type": "text", "text": "x" * (_OFFLOAD_MIN_CHARS + 10)}]
    result = ToolMessage(content=blocks, tool_call_id="tc1")
    out = mw.wrap_tool_call(_request(), lambda _req: result)
    assert out.content == blocks
    assert out.artifact is None

    cmd = Command()
    assert mw.wrap_tool_call(_request(), lambda _req: cmd) is cmd


def test_offload_never_breaks_tool_call() -> None:
    mw = OctopUiOffloadMiddleware()
    result = _big_message()
    with patch(
        "octop.infra.agents.middleware.octop_ui_offload.json.loads",
        side_effect=RuntimeError("boom"),
    ):
        out = mw.wrap_tool_call(_request(), lambda _req: result)
    assert out is result
    assert out.artifact is None
