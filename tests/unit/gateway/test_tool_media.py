"""tests/unit/test_tool_media.py"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from harness_agent.backends import resolve_backend
from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.backend.resolver import default_agent_backend_spec
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


def _default_virtual_workspace(root: str) -> BackendWorkspace:
    """BackendWorkspace matching Octop's platform default agent backend.

    POSIX keeps host-rooted shell access; harness scopes deepagents artifacts
    to the agent workspace. Windows scopes the local-shell root to the
    agent workspace so virtual-mode uploads stay on the same drive.
    """
    spec = default_agent_backend_spec(Path(root))
    return BackendWorkspace(resolve_backend(spec, workspace_dir=root), root)


def test_iter_media_blocks_supports_workbuddy_generation_envelopes() -> None:
    content = json.dumps(
        {
            "type": "image_gen_tool_result",
            "images": [
                {
                    "path": "generated/images/a.png",
                    "localPath": "/private/a.png",
                    "mediaType": "image/png",
                }
            ],
        }
    )

    assert iter_media_blocks(content) == [
        {
            "type": "image",
            "path": "generated/images/a.png",
            "filename": "a.png",
            "media_type": "image/png",
            "source": {
                "type": "url",
                "url": "generated/images/a.png",
                "media_type": "image/png",
            },
        }
    ]


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
        workspace = _default_virtual_workspace(ws)
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
                    "name": "desktop_screenshot",
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
        assert parsed["preview_url"].startswith("/api/agents/agent-1/media/preview")
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
                    "name": "desktop_screenshot",
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
        assert frames[0]["preview_url"].startswith("/api/agents/agent-1/media/preview")
        assert "file%" in frames[0]["preview_url"] or "source=" in frames[0]["preview_url"]


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
                    "name": "send_file_to_user",
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
    assert enriched["preview_url"].startswith("/api/agents/agent-x/media/preview?")
    assert enriched["source"]["url"] == enriched["preview_url"]
    assert enriched["path"] == "outbound/chart.png"
    assert enriched["filename"] == "chart.png"


@pytest.mark.asyncio
async def test_enrich_send_file_keeps_absolute_path_without_copy() -> None:
    """send_file with a host-absolute path must keep that path (no outbound copy).

    Dashboard download already passes ``file://`` to BackendWorkspace, which
    can read absolute paths directly.
    """
    with tempfile.TemporaryDirectory() as ws:
        workspace = _workspace(ws, virtual_mode=False)
        generated = Path(ws) / "generated" / "water-ppt"
        generated.mkdir(parents=True)
        pptx = generated / "保护地球节约用水.pptx"
        pptx.write_bytes(b"PKDATA")
        abs_path = str(pptx.resolve())
        chunk = {
            "type": "tool_result",
            "messages": [
                {
                    "name": "send_file_to_user",
                    "content": {
                        "type": "file",
                        "source": {
                            "type": "url",
                            "url": Path(abs_path).as_uri(),
                            "media_type": (
                                "application/vnd.openxmlformats-officedocument"
                                ".presentationml.presentation"
                            ),
                        },
                        "filename": "保护地球节约用水.pptx",
                    },
                },
            ],
        }
        enriched = await enrich_tool_result_with_backend(
            chunk,
            agent_id="main",
            workspace=workspace,
        )
        content = enriched["messages"][0]["content"]
        assert isinstance(content, dict)
        assert content["type"] == "file"
        assert content.get("path") == abs_path
        assert content["filename"] == "保护地球节约用水.pptx"
        assert "preview_url" not in content
        assert "source" not in content
        outbound = Path(ws) / "outbound"
        assert not outbound.exists() or list(outbound.iterdir()) == []


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
                    "name": "send_file_to_user",
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
    assert url.startswith("/api/agents/W4MFVJ/media/preview?")
    assert "file%" in url or "source=" in url


@pytest.mark.asyncio
async def test_resolve_preview_keeps_host_absolute_screenshot() -> None:
    """Browser screenshots under agent outbound/ must load via absolute path."""
    from deepagents.backends.local_shell import LocalShellBackend
    from harness_agent.backends.workspace import BackendWorkspace

    from octop.infra.gateway.media.backend_files import resolve_preview_payload

    with tempfile.TemporaryDirectory() as ws:
        shots = Path(ws) / "outbound" / "screenshots"
        shots.mkdir(parents=True)
        png = shots / "harness-abs.png"
        png.write_bytes(b"\x89PNG\r\n" + b"x" * 64)
        backend = LocalShellBackend(root_dir="/", virtual_mode=True)
        workspace = BackendWorkspace(backend, ws)
        # Tool returned an absolute file:// path — pass it through unchanged.
        payload = await resolve_preview_payload(
            source=png.as_uri(),
            workspace=workspace,
            mime_hint="image/png",
        )
        assert payload is not None
        data, mime = payload
        assert data.startswith(b"\x89PNG")
        assert mime == "image/png"


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


@pytest.mark.parametrize("prefix", ["", "See ", '"', "'", "(", "\n"])
def test_plain_text_outbound_image_at_token_boundary(prefix: str) -> None:
    from octop.infra.gateway.media.tool_media import _plain_text_image_path

    path = "/workspace/outbound/screenshots/chart.PNG"
    assert _plain_text_image_path(f"{prefix}{path})") == path


def test_plain_text_image_scan_handles_long_web_output() -> None:
    from octop.infra.gateway.media.tool_media import enrich_tool_output_string_sync

    # A long URL/encoded token without an image used to stall the event loop.
    text = "Fetched page: https://example.com/" + "a" * 100_000
    started = time.perf_counter()
    assert enrich_tool_output_string_sync(text, agent_id="A1") == text
    assert time.perf_counter() - started < 1.0


def test_is_media_push_tool_allowlist() -> None:
    from octop.infra.gateway.media.tool_media import is_media_push_tool

    assert is_media_push_tool("send_file_to_user")
    assert is_media_push_tool("namespace/desktop_screenshot")
    assert is_media_push_tool("mobile_screenshot")
    assert is_media_push_tool("generate_image")
    assert not is_media_push_tool("write_file")
    assert not is_media_push_tool("read_file")
    assert not is_media_push_tool("browser_use")
    assert not is_media_push_tool(None)


@pytest.mark.asyncio
async def test_attachment_frames_skip_non_delivery_tools() -> None:
    """write_file / read_file media-shaped results must not push to the user."""
    with tempfile.TemporaryDirectory() as ws:
        workspace = _workspace(ws)
        await workspace.aupload_bytes(f"{OUTBOUND_DIR}/old.png", b"PNG")
        media = {
            "type": "image",
            "source": {
                "type": "url",
                "url": f"file://{ws}/{OUTBOUND_DIR}/old.png",
                "media_type": "image/png",
            },
            "filename": "old.png",
        }
        for tool_name in ("write_file", "read_file", "web_fetch"):
            chunk = {
                "type": "tool_result",
                "messages": [{"name": tool_name, "content": media}],
            }
            frames = [
                f
                async for f in attachment_frames_from_tool_result(
                    chunk,
                    agent_id="agent-1",
                    workspace=workspace,
                )
            ]
            assert frames == [], tool_name


@pytest.mark.asyncio
async def test_plain_text_media_invent_only_for_delivery_tools() -> None:
    with tempfile.TemporaryDirectory() as ws:
        shots = Path(ws) / "outbound" / "screenshots"
        shots.mkdir(parents=True)
        png = shots / "shot.png"
        png.write_bytes(b"\x89PNG\r\n")
        workspace = _workspace(ws)
        text = f"Screenshot saved to {png}"

        write_chunk = {
            "type": "tool_result",
            "messages": [{"name": "write_file", "content": text}],
        }
        write_enriched = await enrich_tool_result_with_backend(
            write_chunk,
            agent_id="A1",
            workspace=workspace,
        )
        assert write_enriched["messages"][0]["content"] == text

        shot_chunk = {
            "type": "tool_result",
            "messages": [{"name": "desktop_screenshot", "content": text}],
        }
        shot_enriched = await enrich_tool_result_with_backend(
            shot_chunk,
            agent_id="A1",
            workspace=workspace,
        )
        content = shot_enriched["messages"][0]["content"]
        assert content != text
        frames = [
            f
            async for f in attachment_frames_from_tool_result(
                shot_enriched,
                agent_id="A1",
                workspace=workspace,
            )
        ]
        assert len(frames) == 1
        assert frames[0]["kind"] == "image"


def test_dedup_tool_result_messages_skips_replayed_ids() -> None:
    from octop.infra.gateway.media.tool_media import dedup_tool_result_messages

    emitted: set[str] = set()
    first = {
        "type": "tool_result",
        "messages": [
            {"tool_call_id": "c1", "name": "send_file_to_user", "content": "a"},
            {"tool_call_id": "c2", "name": "write_file", "content": "b"},
        ],
    }
    kept = dedup_tool_result_messages(first, emitted)
    assert kept is not None
    assert len(kept["messages"]) == 2
    assert emitted == {"c1", "c2"}

    replay = {
        "type": "tool_result",
        "messages": [
            {"tool_call_id": "c1", "name": "send_file_to_user", "content": "a"},
            {"tool_call_id": "c3", "name": "send_file_to_user", "content": "c"},
        ],
    }
    kept2 = dedup_tool_result_messages(replay, emitted)
    assert kept2 is not None
    assert [m["tool_call_id"] for m in kept2["messages"]] == ["c3"]
    assert emitted == {"c1", "c2", "c3"}

    assert dedup_tool_result_messages(first, emitted) is None


@pytest.mark.asyncio
async def test_iter_dashboard_attachment_frames_requires_live_tool_call() -> None:
    """Historical Overwrite dumps before any tool_call_chunk must not push."""
    from octop.infra.gateway.media.tool_media import iter_dashboard_attachment_frames

    with tempfile.TemporaryDirectory() as ws:
        workspace = _workspace(ws)
        await workspace.aupload_bytes(f"{OUTBOUND_DIR}/prior.png", b"PNG")
        chunk = {
            "type": "tool_result",
            "messages": [
                {
                    "tool_call_id": "old-1",
                    "name": "send_file_to_user",
                    "content": {
                        "type": "image",
                        "source": {
                            "type": "url",
                            "url": f"file://{ws}/{OUTBOUND_DIR}/prior.png",
                            "media_type": "image/png",
                        },
                        "filename": "prior.png",
                        "path": f"{OUTBOUND_DIR}/prior.png",
                    },
                },
            ],
        }
        emitted_ids: set[str] = set()
        emitted_keys: set[str] = set()
        frames = [
            f
            async for f in iter_dashboard_attachment_frames(
                chunk,
                agent_id="agent-1",
                workspace=workspace,
                saw_tool_call=False,
                emitted_media_ids=emitted_ids,
                emitted_attachment_keys=emitted_keys,
            )
        ]
        assert frames == []
        assert emitted_ids == set()

        frames_live = [
            f
            async for f in iter_dashboard_attachment_frames(
                chunk,
                agent_id="agent-1",
                workspace=workspace,
                saw_tool_call=True,
                emitted_media_ids=emitted_ids,
                emitted_attachment_keys=emitted_keys,
            )
        ]
        assert len(frames_live) == 1
        assert emitted_ids == {"old-1"}

        # Same path via a new tool_call_id must not push again.
        replay = {
            "type": "tool_result",
            "messages": [
                {
                    "tool_call_id": "new-2",
                    "name": "send_file_to_user",
                    "content": {
                        "type": "image",
                        "source": {
                            "type": "url",
                            "url": f"file://{ws}/{OUTBOUND_DIR}/prior.png",
                            "media_type": "image/png",
                        },
                        "filename": "prior.png",
                        "path": f"{OUTBOUND_DIR}/prior.png",
                    },
                },
            ],
        }
        frames_dup_path = [
            f
            async for f in iter_dashboard_attachment_frames(
                replay,
                agent_id="agent-1",
                workspace=workspace,
                saw_tool_call=True,
                emitted_media_ids=emitted_ids,
                emitted_attachment_keys=emitted_keys,
            )
        ]
        assert frames_dup_path == []


def test_attachment_frame_dedup_key_prefers_path() -> None:
    from octop.infra.gateway.media.tool_media import attachment_frame_dedup_key

    assert (
        attachment_frame_dedup_key(
            {"path": "outbound/a.png", "preview_url": "/api/x", "url": "/api/y"}
        )
        == "path:outbound/a.png"
    )
    assert attachment_frame_dedup_key({"preview_url": "/api/x"}) == "url:/api/x"
