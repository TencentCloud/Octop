"""Workspace I/O path resolution for download / file APIs."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from octop_harness.backends import resolve_backend
from octop_harness.backends.workspace import BackendWorkspace

from octop.api.routers.workspace import _assert_workspace_mutable, _workspace_io_path
from octop.infra.errors import OctopError


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


def _local_workspace(tmp: str) -> BackendWorkspace:
    return BackendWorkspace(
        resolve_backend({"type": "local_shell", "virtual_mode": True}, workspace_dir=tmp),
        tmp,
    )


def test_mutation_outside_workspace_is_forbidden() -> None:
    """The write endpoints' spelling: host-absolute under ``from_workspace=false``.

    ``from_workspace=true`` deliberately reads a leading ``/`` as workspace-relative,
    so the escape only exists on the default (false) path the mutations use.
    """
    with tempfile.TemporaryDirectory() as tmp:
        ws = _local_workspace(tmp)
        outside = Path(tmp).parent / "outside.txt"
        for spelling in (f"file://{outside}", str(outside)):
            with pytest.raises(OctopError):
                _assert_workspace_mutable(spelling, workspace=ws, from_workspace=False)


def test_mutation_inside_workspace_file_url_allowed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ws = _local_workspace(tmp)
        target = Path(tmp) / "a.md"
        # ``as_uri()`` yields the platform-correct spelling (``file:///C:/…`` on
        # Windows); a hand-built ``file://{path}`` would parse its drive as netloc.
        assert _assert_workspace_mutable(target.as_uri(), workspace=ws) == str(target)


def test_sandbox_workspace_accepts_host_absolute_spelling() -> None:
    """A Docker/OpenSandbox agent keeps its content inside the sandbox.

    ``/workspace/x.md`` is the in-container workspace key there — clamped to the
    sandbox root by the backend — not a host path, so the host containment check
    must not reject it (the dashboard sends exactly this spelling via ``file://``).
    """
    ws = SimpleNamespace(
        backend=SimpleNamespace(sandbox_fs=True),
        workspace_dir="/host/agents/main",
    )
    assert _assert_workspace_mutable("file:///workspace/x.md", workspace=ws) == "/workspace/x.md"
    assert _assert_workspace_mutable("/x.md", workspace=ws) == "x.md"
