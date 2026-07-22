"""Workspace I/O path resolution for download / file APIs."""

from __future__ import annotations

from octop.api.routers.workspace import _workspace_io_path


def test_from_workspace_false_slash_is_host_absolute() -> None:
    abs_path = "/Users/jubaoliang/Desktop/IronMan_PPT/钢铁侠.pptx"
    assert _workspace_io_path(abs_path, from_workspace=False) == abs_path
    assert _workspace_io_path("/logo.png", from_workspace=False) == "/logo.png"


def test_from_workspace_true_slash_is_workspace_relative() -> None:
    assert _workspace_io_path("/logo.png", from_workspace=True) == "logo.png"
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


def test_default_from_workspace_is_false() -> None:
    assert _workspace_io_path("/Users/me/a.pptx") == "/Users/me/a.pptx"
