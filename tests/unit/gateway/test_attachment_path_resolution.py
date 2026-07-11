"""Verify attachment workspace-path behaviour for LLM filesystem tools.

Documents the gap between inbound attachment storage (BackendWorkspace) and
deepagents filesystem tools under Octop's default backend (root_dir='/').
"""

from __future__ import annotations

import base64
import os
import re
import tempfile
from pathlib import Path

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from deepagents.backends.utils import validate_path
from harness_agent.backends import DEFAULT_BACKEND_SPEC, resolve_backend
from harness_agent.backends.workspace import BackendWorkspace
from harness_gateway.models import ImageContent, InboundMessage

from octop.api.common.attachments import save_attachment
from octop.infra.agents.middleware.binary_read_guard import read_file_block_reason
from octop.infra.backend.resolver import default_agent_backend_spec
from octop.infra.gateway.media.attachment_hints import format_attachment_path_hint
from octop.infra.gateway.media.inbound_store import resolve_inbound_attachment_path, write_inbound
from octop.infra.gateway.media.ingress import AgentBackedMediaBackend
from octop.infra.gateway.process.harness_request import build_content_from_message
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.gateway.ws import WS_CHANNEL_ID


def _octop_default_agent_workspace(ws_dir: str) -> BackendWorkspace:
    """Mirror production default backend for BackendWorkspace I/O."""
    ws_path = Path(ws_dir)
    backend = resolve_backend(default_agent_backend_spec(ws_path), workspace_dir=ws_dir)
    return BackendWorkspace(backend, ws_dir)


def _storage_only_workspace(ws_dir: str) -> BackendWorkspace:
    """Existing attachment unit tests: local backend without virtual path semantics."""
    backend = LocalShellBackend(root_dir=ws_dir, virtual_mode=False)
    return BackendWorkspace(backend, ws_dir)


@pytest.mark.asyncio
async def test_upload_stores_timestamped_path_keeps_display_filename() -> None:
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = _storage_only_workspace(ws_dir)
        stored = await save_attachment(
            workspace,
            owner_id=1,
            filename="我的报告.pdf",
            media_type="application/pdf",
            data=b"%PDF-1.4",
        )
        assert stored.data_path.startswith("inbound/")
        assert re.search(r"/\d{10,}_我的报告\.pdf$", stored.data_path)
        assert stored.filename == "我的报告.pdf"


@pytest.mark.asyncio
async def test_hint_uses_backend_resolve_path_absolute() -> None:
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = _storage_only_workspace(ws_dir)
        stored = await write_inbound(
            workspace,
            b"%PDF-1.4",
            filename="report.pdf",
            media_type="application/pdf",
        )
        resolved = resolve_inbound_attachment_path(workspace, stored.path)
        hint = format_attachment_path_hint(
            filename="report.pdf",
            path=resolved,
            media_type="application/pdf",
        )
        assert f"Workspace path: {resolved}" in hint
        assert resolved == os.path.realpath(os.path.join(ws_dir, stored.path))


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="Documents POSIX default root_dir=/ behavior")
async def test_octop_default_backend_tool_path_misses_uploaded_file() -> None:
    """Production: file on disk under workspace, but ls/read_file use host /inbound/…"""
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = _octop_default_agent_workspace(ws_dir)
        stored = await write_inbound(
            workspace,
            b"%PDF-1.4",
            filename="report.pdf",
            media_type="application/pdf",
        )
        disk_path = os.path.join(ws_dir, stored.path)
        assert os.path.isfile(disk_path), "BackendWorkspace should persist under agent workspace"

        tool_path = validate_path(stored.path)
        assert tool_path == f"/{stored.path}"

        backend = workspace.backend
        ls_result = backend.ls(tool_path)
        assert ls_result.entries in (None, [])

        read_result = backend.read(tool_path, offset=0, limit=100)
        assert read_result.error is not None or read_result.file_data is None

        # Octop ingress layer can still read the same attachment
        data = await workspace.adownload_bytes(stored.path)
        assert data == b"%PDF-1.4"


@pytest.mark.asyncio
async def test_ai_guessing_original_filename_fails_on_disk() -> None:
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = _storage_only_workspace(ws_dir)
        await write_inbound(
            workspace,
            b"%PDF-1.4",
            filename="report.pdf",
            media_type="application/pdf",
        )
        assert not os.path.isfile(os.path.join(ws_dir, "inbound", "report.pdf"))


def test_read_file_blocked_for_pdf_inbound_even_with_correct_path() -> None:
    reason = read_file_block_reason("inbound/1783510288_report.pdf")
    assert reason is not None
    assert "read_file blocked" in reason


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="Documents POSIX default root_dir=/ behavior")
async def test_default_backend_execute_cwd_is_host_root_not_workspace() -> None:
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = BackendWorkspace(
            resolve_backend(DEFAULT_BACKEND_SPEC, workspace_dir=ws_dir), ws_dir
        )
        assert str(workspace.backend.cwd) == "/"


@pytest.mark.asyncio
async def test_image_materialize_keeps_workspace_path_for_history() -> None:
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = _storage_only_workspace(ws_dir)
        stored = await write_inbound(
            workspace,
            b"png-bytes",
            filename="chart.png",
            media_type="image/png",
        )
        backend = AgentBackedMediaBackend(workspace)
        msg = InboundMessage(
            channel_id=WS_CHANNEL_ID,
            channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            content=[
                ImageContent(
                    local_path=stored.path,
                    mime_type="image/png",
                    alt_text="chart.png",
                )
            ],
        )
        content = await build_content_from_message(msg, media_backend=backend)
        assert isinstance(content, list)
        img = next(b for b in content if b.get("type") == "image_url")
        assert img["workspace_path"] == stored.path
        assert img["workspace_path"] == stored.path
        url = img["image_url"]["url"]
        assert base64.b64decode(url.split(",", 1)[1]) == b"png-bytes"
