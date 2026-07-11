"""tests/unit/test_media_preview.py"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.gateway.media.backend_files import (
    media_preview_url,
    resolve_preview_payload,
)


def test_media_preview_url_encodes_source() -> None:
    src = "file:///tmp/a.png"
    url = media_preview_url("agent-1", src, "image/png")
    assert url.startswith("/api/agents/agent-1/media/preview?")
    assert "file%3A%2F%2F" in url
    assert "mime_type=image%2Fpng" in url


@pytest.mark.asyncio
async def test_resolve_preview_from_outbound_screenshots() -> None:
    with tempfile.TemporaryDirectory() as ws:
        shots = Path(ws) / "outbound" / "screenshots"
        shots.mkdir(parents=True)
        png = shots / "harness.png"
        png.write_bytes(b"\x89PNG\r\n")
        backend = LocalShellBackend(root_dir=ws, virtual_mode=True)
        workspace = BackendWorkspace(backend, ws)
        payload = await resolve_preview_payload(
            source=png.as_uri(),
            workspace=workspace,
            mime_hint="image/png",
        )
        assert payload is not None
        data, mime = payload
        assert data == b"\x89PNG\r\n"
        assert mime == "image/png"


@pytest.mark.asyncio
async def test_resolve_preview_from_tmp_screenshot() -> None:
    with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as ext_dir:
        png = Path(ext_dir) / f"orca-test-preview-{time.time_ns()}.png"
        png.write_bytes(b"\x89PNG\r\n")
        backend = LocalShellBackend(root_dir=ws, virtual_mode=True)
        workspace = BackendWorkspace(backend, ws)
        payload = await resolve_preview_payload(
            source=png.as_uri(),
            workspace=workspace,
            mime_hint="image/png",
        )
        assert payload is not None
        data, mime = payload
        assert data == b"\x89PNG\r\n"
        assert mime == "image/png"
