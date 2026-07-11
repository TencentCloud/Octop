"""tests/unit/test_tool_media.py"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.gateway.media.backend_files import (
    ensure_workspace_media_path,
)
from octop.infra.gateway.media.constants import INBOUND_DIR, OUTBOUND_DIR
from octop.infra.gateway.media.ingress import AgentBackedMediaBackend
from octop.infra.gateway.media.tool_media import (
    attachment_frames_from_tool_result,
    enrich_media_block_preview,
    enrich_tool_result_with_backend,
    iter_media_blocks,
)


def _workspace(root: str, *, virtual_mode: bool = False) -> BackendWorkspace:
    backend = LocalShellBackend(root_dir=root, virtual_mode=virtual_mode)
    return BackendWorkspace(backend, root)


@pytest.mark.asyncio
async def test_workspace_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as ws:
        workspace = _workspace(ws)
        await workspace.aupload_bytes(f"{OUTBOUND_DIR}/a.png", b"PNG")
        data = await workspace.adownload_bytes(f"{OUTBOUND_DIR}/a.png")
        assert data == b"PNG"


@pytest.mark.asyncio
async def test_import_external_file_via_workspace() -> None:
    with tempfile.TemporaryDirectory() as ws:
        external = Path(tempfile.mkdtemp()) / "shot.png"
        external.write_bytes(b"\x89PNG\r\n")
        workspace = _workspace(ws)
        rel = await ensure_workspace_media_path(
            workspace,
            external.as_uri(),
            filename="shot.png",
            mime="image/png",
        )
        assert rel is not None
        assert rel.startswith(f"{OUTBOUND_DIR}/")
        data = await workspace.adownload_bytes(rel)
        assert data == b"\x89PNG\r\n"


@pytest.mark.asyncio
async def test_import_external_file_virtual_mode() -> None:
    with tempfile.TemporaryDirectory() as ws:
        external = Path(tempfile.mkdtemp()) / "harness-browser.png"
        external.write_bytes(b"\x89PNG\r\n")
        workspace = _workspace(ws, virtual_mode=True)
        rel = await ensure_workspace_media_path(
            workspace,
            external.as_uri(),
            filename="harness-browser.png",
            mime="image/png",
        )
        assert rel is not None
        assert rel.startswith(f"{OUTBOUND_DIR}/")
        data = await workspace.adownload_bytes(rel)
        assert data == b"\x89PNG\r\n"


@pytest.mark.asyncio
async def test_attachment_frame_virtual_mode_uses_download_url() -> None:
    with tempfile.TemporaryDirectory() as ws:
        external = Path(tempfile.mkdtemp()) / "harness.png"
        external.write_bytes(b"IMG")
        workspace = _workspace(ws, virtual_mode=True)
        chunk = {
            "type": "tool_result",
            "messages": [
                {
                    "content": json.dumps(
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": external.as_uri(),
                                "media_type": "image/png",
                            },
                            "filename": "harness.png",
                        },
                    ),
                },
            ],
        }
        enriched = await enrich_tool_result_with_backend(
            chunk,
            agent_id="agent-1",
            workspace=workspace,
        )
        content = enriched["messages"][0]["content"]
        parsed = json.loads(content)
        assert parsed["preview_url"].startswith("/api/agents/agent-1/workspace/download")
        assert parsed["source"]["url"] == parsed["preview_url"]
        assert parsed.get("path") in (None, "outbound") or (
            isinstance(parsed.get("path"), str) and parsed["path"].startswith("outbound/")
        )
        assert "/home/" not in json.dumps(parsed)
        assert not str(parsed.get("path") or "").startswith("/api/")
        frames = [
            f
            async for f in attachment_frames_from_tool_result(
                enriched,
                agent_id="agent-1",
                workspace=workspace,
            )
        ]
        assert len(frames) == 1
        assert "data" not in frames[0]
        assert frames[0]["preview_url"] == parsed["preview_url"]


@pytest.mark.asyncio
async def test_attachment_frame_uses_workspace_download_url() -> None:
    with tempfile.TemporaryDirectory() as ws:
        external = Path(tempfile.mkdtemp()) / "harness.png"
        external.write_bytes(b"IMG")
        workspace = _workspace(ws, virtual_mode=False)
        chunk = {
            "type": "tool_result",
            "messages": [
                {
                    "content": json.dumps(
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": external.as_uri(),
                                "media_type": "image/png",
                            },
                            "filename": "harness.png",
                        },
                    ),
                },
            ],
        }
        enriched = await enrich_tool_result_with_backend(
            chunk,
            agent_id="agent-1",
            workspace=workspace,
        )
        frames = [
            f
            async for f in attachment_frames_from_tool_result(
                enriched,
                agent_id="agent-1",
                workspace=workspace,
            )
        ]
        assert len(frames) == 1
        assert frames[0]["type"] == "attachment"
        assert frames[0]["kind"] == "image"
        assert "data" not in frames[0]
        assert frames[0]["preview_url"].startswith("/api/agents/agent-1/workspace/download")
        assert OUTBOUND_DIR in frames[0]["preview_url"]


def test_iter_media_blocks_single_object() -> None:
    blocks = iter_media_blocks('{"type": "image", "source": {"type": "url", "url": "https://x"}}')
    assert len(blocks) == 1


def test_iter_media_blocks_dict_content() -> None:
    block = {
        "type": "image",
        "source": {"type": "url", "url": "file:///tmp/shot.png", "media_type": "image/png"},
    }
    assert len(iter_media_blocks(block)) == 1


@pytest.mark.asyncio
async def test_enrich_send_file_dict_content() -> None:
    with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as ext_dir:
        png = Path(ext_dir) / f"orca-test-send-file-{time.time_ns()}.png"
        png.write_bytes(b"\x89PNG\r\n")
        workspace = _workspace(ws, virtual_mode=True)
        chunk = {
            "type": "tool_result",
            "messages": [
                {
                    "content": {
                        "type": "image",
                        "source": {
                            "type": "url",
                            "url": png.as_uri(),
                            "media_type": "image/png",
                        },
                        "filename": png.name,
                    },
                },
            ],
        }
        enriched = await enrich_tool_result_with_backend(
            chunk,
            agent_id="agent-1",
            workspace=workspace,
        )
        content = enriched["messages"][0]["content"]
        assert isinstance(content, dict)
        assert content.get("preview_url")
        assert content["source"]["url"] == content["preview_url"]
        assert content["filename"] == png.name
        assert not str(content.get("path") or "").startswith("/api/")
        assert "/home/" not in json.dumps(content, ensure_ascii=False)
        frames = [
            f
            async for f in attachment_frames_from_tool_result(
                enriched,
                agent_id="agent-1",
                workspace=workspace,
            )
        ]
        assert len(frames) == 1


def test_agent_backed_media_backend_inbound_fragments() -> None:
    from unittest.mock import MagicMock

    workspace = BackendWorkspace(MagicMock(), "/tmp/ws")
    media = AgentBackedMediaBackend(workspace)

    assert media._inbound_fragment("outbound/img.png") == "outbound/img.png"
    assert media._inbound_fragment("inbound/img.png") == "inbound/img.png"
    assert media._inbound_fragment("/outbound/img.png") == "outbound/img.png"
    assert media._inbound_fragment("img.png") == f"{INBOUND_DIR}/img.png"
    assert media._inbound_fragment("img.png") != f"{OUTBOUND_DIR}/img.png"


def testenrich_media_block_preview_outbound() -> None:
    block = {
        "type": "image",
        "source": {
            "type": "url",
            "url": "file:///tmp/workspace/outbound/chart.png",
            "media_type": "image/png",
        },
        "filename": "chart.png",
        "path": "/tmp/workspace/outbound/chart.png",
    }
    enriched = enrich_media_block_preview(block, agent_id="agent-x")
    assert enriched["preview_url"].startswith("/api/agents/agent-x/workspace/download?path=")
    assert enriched["source"]["url"] == enriched["preview_url"]
    assert enriched["path"] == "outbound/chart.png"
    assert enriched["filename"] == "chart.png"


@pytest.mark.asyncio
async def test_enrich_send_file_rewrites_path_to_dashboard_api() -> None:
    """Host path from send_file must become workspace/download API for dashboard."""
    with tempfile.TemporaryDirectory() as ws:
        workspace = _workspace(ws, virtual_mode=False)
        outbound = Path(ws) / "outbound"
        outbound.mkdir()
        pptx = outbound / "1783513904_地球介绍.pptx"
        pptx.write_bytes(b"PKDATA")
        chunk = {
            "type": "tool_result",
            "messages": [
                {
                    "content": {
                        "type": "file",
                        "source": {
                            "type": "url",
                            "url": pptx.as_uri(),
                            "media_type": (
                                "application/vnd.openxmlformats-officedocument"
                                ".presentationml.presentation"
                            ),
                        },
                        "filename": "地球介绍.pptx",
                        "path": "outbound/1783513904_地球介绍.pptx",
                    },
                },
            ],
        }
        enriched = await enrich_tool_result_with_backend(
            chunk,
            agent_id="Y9F9E6",
            workspace=workspace,
        )
        content = enriched["messages"][0]["content"]
        assert isinstance(content, dict)
        assert "preview_url" not in content
        assert "source" not in content
        assert content["path"] == "outbound/1783513904_地球介绍.pptx"
        assert content["filename"] == "地球介绍.pptx"
        assert content.get("media_type", "").endswith("presentation")
        assert "/home/" not in json.dumps(content, ensure_ascii=False)
        assert not str(content["path"]).startswith("/api/")


def test_dashboard_media_url_uses_path_agent_id() -> None:
    from octop.infra.gateway.media.backend_files import dashboard_media_url

    path = "file:///Users/me/.octop/agents/W4MFVJ/outbound/screenshots/harness.png"
    url = dashboard_media_url("6X3Z7C", path)
    assert url is not None
    assert url.startswith("/api/agents/W4MFVJ/workspace/download?")
    assert "outbound%2Fscreenshots%2Fharness.png" in url or "screenshots" in url


@pytest.mark.asyncio
async def test_enrich_plain_text_screenshot_output() -> None:
    from octop.infra.gateway.media.tool_media import enrich_tool_output_string

    text = (
        "Screenshot saved to /Users/me/.octop/agents/A1/outbound/screenshots/harness.png "
        "(116 KB, 1440x900)"
    )
    enriched = await enrich_tool_output_string(
        text,
        agent_id="A1",
        workspace=None,
    )
    assert enriched != text
    parsed = json.loads(enriched)
    assert isinstance(parsed, list)
    assert parsed[0]["type"] == "text"
    assert parsed[1]["type"] == "image"
    assert parsed[1]["preview_url"].startswith("/api/agents/A1/")
