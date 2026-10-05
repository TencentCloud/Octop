"""``pack_agent_memory`` must not leak its staging ``.hmpkg`` temp file.

The sibling endpoints (``adopt`` / ``doctor``) wrap their temp file in a
``try/finally``; the pack endpoint used to create the file with
``delete=False`` and only unlink it at the end of the streaming generator, so
any failure between creation and the end of the download left a multi-MB
``.hmpkg`` behind in the system temp directory.
"""

from __future__ import annotations

import gc
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.api.routers import memory_portable
from octop.infra.errors import OctopError


def _stub_handler_deps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Neutralise the owner/workspace plumbing so the handler reaches ``pack``."""
    import octop_memory.operations.migration.portable.sources as sources_mod

    monkeypatch.setattr(memory_portable, "require_agent_owner_row", lambda *a, **k: None)
    monkeypatch.setattr(memory_portable, "_refuse_postgres_portable", lambda *a, **k: None)
    monkeypatch.setattr(memory_portable, "_agent_config_dict", lambda *a, **k: {})
    monkeypatch.setattr(memory_portable, "resolve_agent_workspace_dir", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        memory_portable, "memory_db_path_for_cfg", lambda *a, **k: tmp_path / "mem.db"
    )
    monkeypatch.setattr(memory_portable, "memory_namespace", lambda *a, **k: "ns")
    monkeypatch.setattr(
        sources_mod,
        "_probe_db",
        lambda *a, **k: [SimpleNamespace(namespace="ns")],
    )
    # Redirect the staging file into the test's own directory so the leftover
    # is observable.
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))


async def test_pack_failure_removes_staging_temp_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import octop_memory.operations.migration.portable as portable_mod

    _stub_handler_deps(monkeypatch, tmp_path)

    def _boom(src: Any, *, out: Path) -> Any:
        assert Path(out).exists(), "staging file should exist before pack runs"
        raise RuntimeError("pack blew up")

    monkeypatch.setattr(portable_mod, "pack", _boom)

    with pytest.raises(OctopError):
        await memory_portable.pack_agent_memory("agt", user=object(), server=object(), as_user=None)

    assert list(tmp_path.glob("*.hmpkg")) == []


async def test_successful_pack_streams_and_removes_staging_temp_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import octop_memory.operations.migration.portable as portable_mod

    _stub_handler_deps(monkeypatch, tmp_path)

    def _pack(src: Any, *, out: Path) -> Any:
        Path(out).write_bytes(b"hmpkg-payload")
        return SimpleNamespace(total_rows=3)

    monkeypatch.setattr(portable_mod, "pack", _pack)

    response = await memory_portable.pack_agent_memory(
        "agt", user=object(), server=object(), as_user=None
    )
    chunks = [chunk async for chunk in response.body_iterator]
    assert b"".join(chunks) == b"hmpkg-payload"
    assert list(tmp_path.glob("*.hmpkg")) == []


async def test_aborted_download_removes_staging_temp_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A client that hangs up mid-download must not strand the staging file."""
    import octop_memory.operations.migration.portable as portable_mod

    _stub_handler_deps(monkeypatch, tmp_path)
    payload = b"x" * (200 * 1024)

    def _pack(src: Any, *, out: Path) -> Any:
        Path(out).write_bytes(payload)
        return SimpleNamespace(total_rows=1)

    monkeypatch.setattr(portable_mod, "pack", _pack)

    response = await memory_portable.pack_agent_memory(
        "agt", user=object(), server=object(), as_user=None
    )
    iterator = response.body_iterator
    first = await iterator.__anext__()
    assert first, "expected a first chunk before aborting"
    assert list(tmp_path.glob("*.hmpkg")), "file should still exist mid-download"
    await iterator.aclose()
    gc.collect()
    assert list(tmp_path.glob("*.hmpkg")) == []
