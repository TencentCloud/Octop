"""Unit tests for gateway media path helpers."""

from __future__ import annotations

from octop.infra.gateway.media.backend_files import (
    dashboard_media_url,
    extract_workspace_rel,
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
    assert url.startswith("/api/agents/W4MFVJ/workspace/download?")
