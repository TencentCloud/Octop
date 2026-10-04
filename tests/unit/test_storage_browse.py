"""Unit tests for storage backend browse helpers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.backend.browse import (
    dispose_all_browse_sessions,
    list_storage_backend_tree,
)
from octop.infra.backend.probe import row_for_probe
from octop.infra.db.repos.backends import BackendRow


@pytest.fixture(autouse=True)
def _reset_browse_sessions() -> None:
    dispose_all_browse_sessions()
    yield
    dispose_all_browse_sessions()


def _row(**kwargs: object) -> BackendRow:
    base = {
        "id": 1,
        "name": "test",
        "kind": "filesystem",
        "endpoint": None,
        "access_key": None,
        "secret_key": None,
        "bucket": None,
        "region": None,
        "config_json": None,
        "note": None,
        "enabled": 1,
        "created_at": 0,
        "updated_at": 0,
    }
    base.update(kwargs)
    return BackendRow(**base)  # type: ignore[arg-type]


def _filesystem_row(root: Path) -> BackendRow:
    """Build a filesystem row; ``json.dumps`` keeps Windows ``\\`` paths valid."""
    return _row(kind="filesystem", config_json=json.dumps({"root_dir": str(root)}))


def test_filesystem_row_keeps_windows_root_dir() -> None:
    from octop.infra.backend.adapter import row_to_backend_spec

    win_root = r"C:\Users\runneradmin\AppData\Local\Temp\data"
    spec = row_to_backend_spec(
        _row(kind="filesystem", config_json=json.dumps({"root_dir": win_root})),
    )
    assert spec is not None
    assert spec["root_dir"] == win_root


def test_row_for_probe_merges_secrets_from_base() -> None:
    base = _row(
        kind="cos",
        access_key="AKIDstored",
        secret_key="SKstored",
        bucket="my-bucket",
        region="ap-guangzhou",
    )
    merged = row_for_probe(
        kind="cos",
        bucket="other-bucket",
        base=base,
    )
    assert merged.bucket == "other-bucket"
    assert merged.access_key == "AKIDstored"
    assert merged.secret_key == "SKstored"


def test_row_for_probe_overrides_secrets_when_provided() -> None:
    base = _row(access_key="AKIDstored", secret_key="SKstored")
    merged = row_for_probe(
        kind="cos",
        access_key="AKIDnew",
        secret_key="SKnew",
        base=base,
    )
    assert merged.access_key == "AKIDnew"
    assert merged.secret_key == "SKnew"


@pytest.mark.asyncio
async def test_list_storage_backend_tree_docker_lists_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Docker kind uses container als; temporary sandbox must be closed."""
    fake_backend = MagicMock()
    fake_backend.als = AsyncMock(
        return_value=MagicMock(
            error=None,
            entries=[
                {"path": "SOUL.md", "is_dir": False, "size": 10},
                {"path": "skills", "is_dir": True},
            ],
        ),
    )
    monkeypatch.setattr(
        "octop.infra.backend.browse.resolve_storage_backend",
        lambda _row: fake_backend,
    )

    entries = await list_storage_backend_tree(_row(kind="docker", bucket="python:3.12-slim"), "/")
    assert len(entries) == 2
    assert entries[0]["path"] == "SOUL.md"
    assert entries[1]["is_dir"] is True
    fake_backend.close.assert_not_called()
    from octop.infra.backend.browse import release_browse_session

    await release_browse_session(1)
    fake_backend.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_list_storage_backend_tree_maps_runtime_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Docker/image failures become ValueError (API 400), not uncaught 500."""
    monkeypatch.setattr(
        "octop.infra.backend.browse.resolve_backend",
        lambda *_a, **_k: (_ for _ in ()).throw(
            RuntimeError(
                "Docker image 'python:3.12-slim' is not available; "
                "run: docker pull python:3.12-slim"
            )
        ),
    )
    with pytest.raises(ValueError, match=r"docker pull python:3\.12-slim"):
        await list_storage_backend_tree(_row(kind="docker", bucket="python:3.12-slim"), "/")


@pytest.mark.asyncio
async def test_list_storage_backend_tree_classifies_object_store_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.infra.backend.browse import StorageBrowseError

    fake_backend = MagicMock()
    fake_backend.als = AsyncMock(
        return_value=MagicMock(
            error=(
                "Error listing '/': An error occurred (NoSuchBucket) when calling "
                "the ListObjectsV2 operation: The specified bucket does not exist."
            ),
            entries=None,
        ),
    )
    monkeypatch.setattr(
        "octop.infra.backend.browse.resolve_storage_backend",
        lambda _row: fake_backend,
    )
    with pytest.raises(StorageBrowseError) as excinfo:
        await list_storage_backend_tree(_row(kind="s3", bucket="missing"), "/")
    assert excinfo.value.classified.message_key == "probe_no_such_bucket"
    assert "NoSuchBucket" not in str(excinfo.value)
    assert "ListObjectsV2" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_list_storage_backend_tree_returns_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.txt").write_text("hi", encoding="utf-8")
    (root / "subdir").mkdir()

    row = _filesystem_row(root)

    fake_backend = MagicMock()
    fake_backend.als = AsyncMock(
        return_value=MagicMock(
            error=None,
            entries=[
                {"path": "a.txt", "is_dir": False, "size": 2},
                {"path": "subdir", "is_dir": True},
            ],
        ),
    )
    monkeypatch.setattr(
        "octop.infra.backend.browse.resolve_storage_backend",
        lambda _row: fake_backend,
    )

    entries = await list_storage_backend_tree(row, "/")
    assert len(entries) == 2
    assert entries[0]["path"] == "a.txt"
    assert entries[1]["is_dir"] is True
    fake_backend.close.assert_not_called()
    from octop.infra.backend.browse import release_browse_session

    await release_browse_session(row.id)
    fake_backend.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_list_storage_backend_tree_uses_als_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """deepagents_backends implements als_info, not als."""
    fake_backend = MagicMock()
    fake_backend.als = AsyncMock(side_effect=NotImplementedError)
    fake_backend.als_info = AsyncMock(
        return_value=[
            {"path": "/", "is_dir": True},
            {"path": "notes.md", "is_dir": False, "size": 4},
        ],
    )
    monkeypatch.setattr(
        "octop.infra.backend.browse.resolve_storage_backend",
        lambda _row: fake_backend,
    )

    entries = await list_storage_backend_tree(_row(kind="s3", bucket="demo"), "/")
    assert entries == [{"path": "notes.md", "is_dir": False, "size": 4}]
    fake_backend.als_info.assert_awaited_once()


@pytest.mark.asyncio
async def test_download_storage_backend_file_reads_bytes(tmp_path: Path) -> None:
    from octop.infra.backend.browse import (
        download_storage_backend_file,
        read_storage_backend_text,
    )

    root = tmp_path / "data"
    root.mkdir()
    # Binary write: Path.write_text() turns \n into \r\n on Windows.
    (root / "note.md").write_bytes(b"# hello\n")
    (root / "blob.bin").write_bytes(b"\x00\xff\xfe")
    row = _filesystem_row(root)

    assert await download_storage_backend_file(row, "/note.md") == b"# hello\n"
    assert await read_storage_backend_text(row, "/note.md") == "# hello\n"
    assert await download_storage_backend_file(row, "/blob.bin") == b"\x00\xff\xfe"


@pytest.mark.asyncio
async def test_read_storage_backend_text_rejects_binary(tmp_path: Path) -> None:
    from octop.infra.backend.browse import StorageBrowseError, read_storage_backend_text

    root = tmp_path / "data"
    root.mkdir()
    (root / "blob.bin").write_bytes(b"\x00\xff\xfe")
    row = _filesystem_row(root)
    with pytest.raises(StorageBrowseError) as excinfo:
        await read_storage_backend_text(row, "/blob.bin")
    assert excinfo.value.classified.message_key == "browse_not_text"


@pytest.mark.asyncio
async def test_download_storage_backend_file_missing(tmp_path: Path) -> None:
    from octop.infra.backend.browse import download_storage_backend_file

    root = tmp_path / "data"
    root.mkdir()
    row = _filesystem_row(root)
    with pytest.raises(FileNotFoundError):
        await download_storage_backend_file(row, "/missing.txt")


@pytest.mark.asyncio
async def test_download_storage_backend_rejects_parent_escape() -> None:
    from octop.infra.backend.browse import download_storage_backend_file

    row = _row(kind="filesystem", config_json='{"root_dir": "/tmp"}')
    with pytest.raises(ValueError, match="invalid path"):
        await download_storage_backend_file(row, "/../secret")


@pytest.mark.asyncio
async def test_download_storage_backend_reuses_backend_until_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.infra.backend.browse import (
        download_storage_backend_file,
        release_browse_session,
    )

    fake_backend = MagicMock()
    fake_backend.adownload_files = None
    fake_backend.download_files = MagicMock(
        return_value=[MagicMock(error=None, content=b"abc", path="/a.txt")]
    )
    resolve = MagicMock(return_value=fake_backend)
    monkeypatch.setattr("octop.infra.backend.browse.resolve_storage_backend", resolve)
    row = _row(kind="s3", bucket="b")
    assert await download_storage_backend_file(row, "/a.txt") == b"abc"
    assert await download_storage_backend_file(row, "/a.txt") == b"abc"
    assert resolve.call_count == 1
    fake_backend.close.assert_not_called()
    await release_browse_session(row.id)
    fake_backend.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_download_preview_rejects_oversize(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.backend.browse import (
        PREVIEW_BYTE_LIMIT,
        StorageBrowseError,
        download_storage_backend_file,
    )

    fake_backend = MagicMock()
    fake_backend.adownload_files = None
    fake_backend.download_files = MagicMock(
        return_value=[
            MagicMock(error=None, content=b"x" * (PREVIEW_BYTE_LIMIT + 1), path="/big.bin")
        ]
    )
    monkeypatch.setattr(
        "octop.infra.backend.browse.resolve_storage_backend",
        lambda _row: fake_backend,
    )
    with pytest.raises(StorageBrowseError) as excinfo:
        await download_storage_backend_file(_row(kind="s3", bucket="b"), "/big.bin", preview=True)
    assert excinfo.value.classified.message_key == "browse_too_large"


def test_resolve_storage_backend_removes_temp_dir_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.infra.backend.browse import resolve_storage_backend

    created: list[str] = []
    real_mkdtemp = tempfile.mkdtemp

    def fake_mkdtemp(*args: object, **kwargs: object) -> str:
        path = real_mkdtemp(*args, **kwargs)
        created.append(path)
        return path

    monkeypatch.setattr("octop.infra.backend.browse.tempfile.mkdtemp", fake_mkdtemp)
    monkeypatch.setattr(
        "octop.infra.backend.browse.resolve_backend",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(ValueError, match="boom"):
        resolve_storage_backend(_row(kind="docker", bucket="python:3.12-slim"))
    assert created
    assert not Path(created[0]).exists()
