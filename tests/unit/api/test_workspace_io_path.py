"""Workspace I/O path resolution for download / file APIs.

SEC-2 durable fix: the HTTP surface no longer accepts a ``from_workspace``
query parameter. Paths always resolve workspace-relative (dashboard
convention: leading ``/`` = workspace root); host-absolute interpretation
exists only for explicit ``file://`` URLs. Internal gateway callers may still
pass ``from_workspace=True`` explicitly for workspace-relative rewrites.
"""

from __future__ import annotations

from octop.api.routers.workspace import _workspace_io_path


def test_leading_slash_always_workspace_relative() -> None:
    # Dashboard convention: '/logo.png' is workspace-root relative.
    assert _workspace_io_path("/logo.png", from_workspace=False) == "logo.png"
    assert _workspace_io_path("/logo.png", from_workspace=True) == "logo.png"


def test_from_workspace_true_slash_is_workspace_relative() -> None:
    assert _workspace_io_path("/outbound/a.pptx", from_workspace=True) == "outbound/a.pptx"
    assert _workspace_io_path("/", from_workspace=True) == "."


def test_relative_without_slash_always_workspace() -> None:
    assert (
        _workspace_io_path("generated/water-ppt/a.pptx", from_workspace=False)
        == "generated/water-ppt/a.pptx"
    )
    assert (
        _workspace_io_path("generated/water-ppt/a.pptx", from_workspace=True)
        == "generated/water-ppt/a.pptx"
    )


def test_file_url_always_host_absolute() -> None:
    assert (
        _workspace_io_path("file:///Users/me/report.pptx", from_workspace=False)
        == "/Users/me/report.pptx"
    )
    assert (
        _workspace_io_path("file:///Users/me/report.pptx", from_workspace=True)
        == "/Users/me/report.pptx"
    )


def test_windows_drive_and_unc_stay_workspace_relative() -> None:
    # SEC-2: drive-letter and UNC forms no longer opt into host-absolute
    # interpretation from the HTTP surface — they resolve workspace-relative
    # like any other leading-slash path.
    assert _workspace_io_path("C:/Users/me/a.pptx", from_workspace=False) == (
        "C:/Users/me/a.pptx"
    ).lstrip("/")
    assert _workspace_io_path("\\\\server/share/a.pptx", from_workspace=False) == (
        "\\\\server/share/a.pptx"
    ).lstrip("\\")
