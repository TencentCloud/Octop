"""Tests for backend resolver helpers."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from deepagents.backends import CompositeBackend
from harness_agent.backends import resolve_backend
from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.backend.resolver import (
    backend_spec_supports_execution,
    default_agent_backend_spec,
)


def test_default_agent_backend_spec_posix_scopes_artifacts_to_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "agents" / "AGT001"
    ws.mkdir(parents=True)
    with patch("octop.infra.backend.resolver.os", SimpleNamespace(name="posix")):
        backend = default_agent_backend_spec(ws)

    assert isinstance(backend, CompositeBackend)
    assert backend.artifacts_root == str(ws.resolve())
    assert backend_spec_supports_execution(backend)
    assert resolve_backend(backend, workspace_dir=ws) is backend

    workspace = BackendWorkspace(backend, ws)
    workspace.mkdir("source")
    source = ws / "source" / "note.txt"
    source.write_text("context summary", encoding="utf-8")
    workspace.move("source", "moved")
    assert (ws / "moved" / "note.txt").read_text(encoding="utf-8") == "context summary"
    workspace.delete("moved")
    assert not (ws / "moved").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX backend paths are required")
def test_default_agent_backend_posix_writes_artifacts_to_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "agents" / "AGT001"
    ws.mkdir(parents=True)

    backend = resolve_backend(default_agent_backend_spec(ws), workspace_dir=ws)

    assert isinstance(backend, CompositeBackend)
    assert backend.artifacts_root == str(ws.resolve())
    history_path = ws / "conversation_history" / "thread.md"
    result = backend.write(str(history_path), "context summary")
    assert result.error is None
    assert history_path.read_text(encoding="utf-8") == "context summary"


def test_default_agent_backend_spec_windows_scopes_to_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "agents" / "AGT001"
    ws.mkdir(parents=True)
    with patch("octop.infra.backend.resolver.os", SimpleNamespace(name="nt")):
        spec = default_agent_backend_spec(ws)
    assert spec == {
        "type": "local_shell",
        "root_dir": str(ws.resolve()),
        "virtual_mode": True,
    }
