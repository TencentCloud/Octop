"""Regression tests for portable pack temp-file cleanup (issue #1638).

``pack_agent_memory`` used to delete its ``.hmpkg`` temp file only after the
stream finished, so a failed pack or a download that the client abandoned left
multi-MB files behind in the system temp directory.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.api.routers import memory_portable as mp
from octop.infra.errors import ErrorCode, OctopError


def _patch_endpoint_deps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mp, "require_agent_owner_row", lambda *_a, **_k: None)
    monkeypatch.setattr(mp, "_refuse_postgres_portable", lambda *_a, **_k: None)
    monkeypatch.setattr(mp, "_agent_config_dict", lambda *_a, **_k: {})
    monkeypatch.setattr(mp, "resolve_agent_workspace_dir", lambda *_a, **_k: tmp_path)
    monkeypatch.setattr(mp, "memory_db_path_for_cfg", lambda *_a, **_k: tmp_path / "mem.db")
    monkeypatch.setattr(mp, "memory_namespace", lambda *_a, **_k: "ns")


def _patch_portable(monkeypatch: pytest.MonkeyPatch, pack: Any) -> None:
    import octop_memory.operations.migration.portable as portable_pkg
    from octop_memory.operations.migration.portable import sources as portable_sources

    monkeypatch.setattr(portable_sources, "_probe_db", lambda *_a, **_k: [])
    monkeypatch.setattr(portable_pkg, "pack", pack)


def _temp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmpdir))
    return tmpdir


async def test_pack_failure_cleans_up_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_endpoint_deps(monkeypatch, tmp_path)
    tmpdir = _temp_dir(tmp_path, monkeypatch)

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("pack failed")

    _patch_portable(monkeypatch, boom)

    with pytest.raises(OctopError) as excinfo:
        await mp.pack_agent_memory("agent-1", user=object(), server=object(), as_user=None)

    assert excinfo.value.code is ErrorCode.INTERNAL_ERROR
    assert list(tmpdir.glob("*.hmpkg")) == []


async def test_successful_pack_streams_then_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_endpoint_deps(monkeypatch, tmp_path)
    tmpdir = _temp_dir(tmp_path, monkeypatch)

    def fake_pack(_src: Any, out: Path) -> SimpleNamespace:
        Path(out).write_bytes(b"hello-package")
        return SimpleNamespace(total_rows=3)

    _patch_portable(monkeypatch, fake_pack)

    response = await mp.pack_agent_memory("agent-1", user=object(), server=object(), as_user=None)
    body = b"".join([chunk async for chunk in response.body_iterator])

    assert body == b"hello-package"
    assert list(tmpdir.glob("*.hmpkg")) == []


def test_interrupted_stream_cleans_up_temp_file(tmp_path: Path) -> None:
    pkg = tmp_path / "agent.hmpkg"
    pkg.write_bytes(b"x" * (65536 * 3 + 7))

    gen = mp._stream_file_and_cleanup(pkg)
    assert next(gen)
    gen.close()  # simulates the client disconnecting mid-download

    assert not pkg.exists()


def test_completed_stream_cleans_up_temp_file(tmp_path: Path) -> None:
    pkg = tmp_path / "agent.hmpkg"
    pkg.write_bytes(b"payload")

    chunks = list(mp._stream_file_and_cleanup(pkg))

    assert b"".join(chunks) == b"payload"
    assert not pkg.exists()
