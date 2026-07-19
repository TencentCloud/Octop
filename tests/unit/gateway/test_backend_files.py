"""Unit tests for gateway media path helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.gateway.media.backend_files import (
    dashboard_media_url,
    ensure_workspace_media_path,
    extract_workspace_rel,
    resolve_preview_payload,
)


def test_extract_workspace_rel_handles_backslashes() -> None:
    rel = extract_workspace_rel(
        r"file:///C:/Users/me/.octop/agents/W4MFVJ/outbound/screenshots/harness.png"
    )
    assert rel == "outbound/screenshots/harness.png"


def test_dashboard_media_url_windows_file_path() -> None:
    url = dashboard_media_url(
        "6X3Z7C",
        r"file:///C:/Users/me/.octop/agents/W4MFVJ/outbound/screenshots/harness.png",
    )
    assert url is not None
    assert url.startswith("/api/agents/W4MFVJ/media/preview?")
    assert "file%3A%2F%2F" in url or "source=file" in url


def test_dashboard_media_url_keeps_host_absolute_screenshot() -> None:
    url = dashboard_media_url(
        "N9TKYG",
        "/home/wally/.octop/agents/N9TKYG/outbound/screenshots/harness.png",
    )
    assert url is not None
    assert "/media/preview?" in url
    assert "N9TKYG" in url
    assert "file%" in url or "outbound" in url


def _workspace(root: str, *, virtual_mode: bool = False) -> BackendWorkspace:
    return BackendWorkspace(
        LocalShellBackend(root_dir=root, virtual_mode=virtual_mode),
        root,
    )


def _deny_host_absolute_downloads(workspace: BackendWorkspace) -> None:
    """Simulate Windows: BackendWorkspace rejects drive-letter / abs host paths."""
    original = workspace.adownload_bytes

    async def _guarded(path: str) -> Any:
        text = str(path).replace("\\", "/")
        if text.startswith(("outbound/", "inbound/", "/outbound/", "/inbound/")):
            return await original(path)
        if text.startswith("/") or (len(text) >= 2 and text[1] == ":"):
            raise PermissionError(f"path {path!r} is outside workspace")
        return await original(path)

    workspace.adownload_bytes = _guarded  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_resolve_preview_uses_workspace_rel_when_abs_denied() -> None:
    with tempfile.TemporaryDirectory() as ws:
        shots = Path(ws) / "outbound" / "screenshots"
        shots.mkdir(parents=True)
        png = shots / "harness.png"
        png.write_bytes(b"\x89PNG\r\n")
        workspace = _workspace(ws, virtual_mode=True)
        _deny_host_absolute_downloads(workspace)

        payload = await resolve_preview_payload(
            source=png.as_uri(),
            workspace=workspace,
            mime_hint="image/png",
        )
        assert payload is not None
        assert payload[0] == b"\x89PNG\r\n"


@pytest.mark.asyncio
async def test_ensure_workspace_media_host_fallback_when_abs_denied() -> None:
    with tempfile.TemporaryDirectory() as ws:
        external = Path(tempfile.mkdtemp()) / "shot.png"
        external.write_bytes(b"\x89PNG\r\n")
        workspace = _workspace(ws)
        _deny_host_absolute_downloads(workspace)

        rel = await ensure_workspace_media_path(
            workspace,
            external.as_uri(),
            filename="shot.png",
            mime="image/png",
        )
        assert rel is not None
        assert rel.startswith("outbound/")
        assert await workspace.adownload_bytes(rel) == b"\x89PNG\r\n"
