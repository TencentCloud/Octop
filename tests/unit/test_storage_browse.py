"""Unit tests for storage backend browse helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.backend.browse import list_storage_backend_tree
from octop.infra.backend.probe import row_for_probe
from octop.infra.db.repos.backends import BackendRow


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
async def test_list_storage_backend_tree_returns_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.txt").write_text("hi", encoding="utf-8")
    (root / "subdir").mkdir()

    row = _row(kind="filesystem", config_json=f'{{"root_dir": "{root}"}}')

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
    fake_backend.close.assert_called_once_with()
